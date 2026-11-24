"""
SIR (Susceptible-Infected-Recovered) epidemic state machine and peer co-location tracking.

Pure Python so it can run on both the Pybricks hub (MicroPython) and host unit tests.
"""

import random

from shared.enums import SIRState, Zone
from shared.models import PeerStatus
from shared.sim_config import (
    INFECTION_CHECK_INTERVAL_MS,
    INFECTION_CONTACT_MS,
    INFECTION_PROB_PER_SEC,
    NO_INFECTED_END_MS,
    PEER_CONTACT_TIMEOUT_MS,
    PEER_STATE_TIMEOUT_MS,
    RECOVERY_DURATION_MS,
)


class SIRSimulation:
    """Tracks this robot's SIR state, zone co-location timers, and peer states."""

    def __init__(self, initial_infected=False):
        self.initial_infected = initial_infected
        self.sir_state = SIRState.INFECTED if initial_infected else SIRState.SUSCEPTIBLE
        self.infected_since_ms = 0 if initial_infected else None
        self.current_zone = Zone.UNKNOWN
        self.peers = {}  # robot_id -> PeerStatus
        self.ever_saw_infected = (self.sir_state == SIRState.INFECTED)
        self.no_infected_since = None

    def reset_run(self):
        """Resets run-scoped peer tracking and infection/end timers."""
        self.peers.clear()
        self.ever_saw_infected = (self.sir_state == SIRState.INFECTED)
        self.infected_since_ms = 0 if self.sir_state == SIRState.INFECTED else None
        self.no_infected_since = None

    def clear_peer_contact(self, other_id=None):
        """Clears co-location contact timers for one peer, or all peers if `other_id` is None."""
        if other_id is None:
            for peer in self.peers.values():
                peer.contact_start_ms = None
                peer.last_roll_ms = None
        elif other_id in self.peers:
            self.peers[other_id].contact_start_ms = None
            self.peers[other_id].last_roll_ms = None

    def observe_peer_packet(self, other_id, other_state, other_zone, now_ms):
        """Records a decoded peer telemetry broadcast."""
        peer = self.peers.get(other_id)
        if peer is None:
            self.peers[other_id] = PeerStatus(
                state=other_state,
                zone=other_zone,
                last_seen_ms=now_ms,
            )
        else:
            peer.state = other_state
            peer.zone = other_zone
            peer.last_seen_ms = now_ms

        if other_state == SIRState.INFECTED:
            self.ever_saw_infected = True

    def expire_stale_peer(self, ch, now_ms):
        """Expires contact and state records for a peer channel that has gone silent."""
        peer = self.peers.get(ch)
        if peer is None:
            return
        silent_ms = now_ms - peer.last_seen_ms
        if silent_ms > PEER_STATE_TIMEOUT_MS:
            self.peers.pop(ch, None)
        elif silent_ms > PEER_CONTACT_TIMEOUT_MS:
            peer.contact_start_ms = None
            peer.last_roll_ms = None

    def has_any_infected(self):
        """Returns True if this robot or any active peer is currently in SIRState.INFECTED."""
        if self.sir_state == SIRState.INFECTED:
            return True
        return any(peer.state == SIRState.INFECTED for peer in self.peers.values())

    def is_finished(self, now_ms):
        """
        Returns True once at least one robot was infected during this run,
        no robot remains infected, and that condition holds for NO_INFECTED_END_MS.
        """
        if self.sir_state == SIRState.INFECTED:
            self.ever_saw_infected = True
        if not self.ever_saw_infected or self.has_any_infected():
            self.no_infected_since = None
            return False

        if self.no_infected_since is None:
            self.no_infected_since = now_ms
            return False

        return (now_ms - self.no_infected_since) >= NO_INFECTED_END_MS

    def _should_roll_infection(self, peer, now_ms):
        """Enforces one infection roll per INFECTION_CHECK_INTERVAL_MS after contact threshold."""
        if peer.last_roll_ms is None:
            peer.last_roll_ms = now_ms
            return True
        if now_ms - peer.last_roll_ms >= INFECTION_CHECK_INTERVAL_MS:
            peer.last_roll_ms += INFECTION_CHECK_INTERVAL_MS
            return True
        return False

    def check_zone_infection(self, now_ms):
        """
        Evaluates co-location with infected peers in the same valid zone.

        If this robot is susceptible and shares a valid zone with an infected peer for
        at least INFECTION_CONTACT_MS, rolls once per second with INFECTION_PROB_PER_SEC.
        Returns the infecting peer's ID if infection occurred, else None.
        """
        if self.sir_state != SIRState.SUSCEPTIBLE or self.current_zone == Zone.UNKNOWN:
            self.clear_peer_contact()
            return None

        for other_id, peer in list(self.peers.items()):
            if now_ms - peer.last_seen_ms > PEER_CONTACT_TIMEOUT_MS:
                peer.contact_start_ms = None
                peer.last_roll_ms = None
                continue

            if peer.state == SIRState.INFECTED and peer.zone == self.current_zone:
                if peer.contact_start_ms is None:
                    peer.contact_start_ms = now_ms
                elif now_ms - peer.contact_start_ms >= INFECTION_CONTACT_MS:
                    if self._should_roll_infection(peer, now_ms) and random.random() < INFECTION_PROB_PER_SEC:
                        self.sir_state = SIRState.INFECTED
                        self.infected_since_ms = now_ms
                        self.ever_saw_infected = True
                        self.clear_peer_contact()
                        return other_id
            else:
                peer.contact_start_ms = None
                peer.last_roll_ms = None

        return None

    def check_recovery(self, now_ms):
        """
        Transitions an infected robot to recovered once it has been infected
        for at least RECOVERY_DURATION_MS. Returns True if recovery occurred.
        """
        if self.sir_state != SIRState.INFECTED:
            return False
        if self.infected_since_ms is None:
            self.infected_since_ms = now_ms
            return False
        if now_ms - self.infected_since_ms >= RECOVERY_DURATION_MS:
            self.sir_state = SIRState.RECOVERED
            self.infected_since_ms = None
            return True
        return False
