"""
SIR (Susceptible-Infected-Recovered) epidemic state machine and peer co-location tracking.

Pure Python so it can run on both the Pybricks hub (MicroPython) and host unit tests.
"""

import random

from shared.sim_config import (
    INFECTION_CHECK_INTERVAL_MS,
    INFECTION_CONTACT_MS,
    INFECTION_PROB_PER_SEC,
    NO_INFECTED_END_MS,
    PEER_CONTACT_TIMEOUT_MS,
    PEER_STATE_TIMEOUT_MS,
    RECOVERY_DURATION_MS,
    STATE_INFECTED,
    STATE_RECOVERED,
    STATE_SUSCEPTIBLE,
    ZONE_UNKNOWN,
)


class SIRSimulation:
    """Tracks this robot's SIR state, zone co-location timers, and peer states."""

    def __init__(self, initial_infected=False):
        self.initial_infected = initial_infected
        self.sir_state = STATE_INFECTED if initial_infected else STATE_SUSCEPTIBLE
        self.infected_since_ms = 0 if initial_infected else None
        self.current_zone = ZONE_UNKNOWN
        self.peer_contact_start = {}
        self.peer_last_seen = {}
        self.peer_last_roll = {}
        self.peer_states = {}
        self.peer_zones = {}
        self.ever_saw_infected = (self.sir_state == STATE_INFECTED)
        self.no_infected_since = None

    def reset_run(self):
        """Resets run-scoped peer tracking and infection/end timers."""
        self.clear_peer_contact()
        self.peer_last_seen.clear()
        self.peer_states.clear()
        self.peer_zones.clear()
        self.ever_saw_infected = (self.sir_state == STATE_INFECTED)
        self.infected_since_ms = 0 if self.sir_state == STATE_INFECTED else None
        self.no_infected_since = None

    def clear_peer_contact(self, other_id=None):
        """Clears co-location contact timers for one peer, or all peers if `other_id` is None."""
        if other_id is None:
            self.peer_contact_start.clear()
            self.peer_last_roll.clear()
        else:
            self.peer_contact_start.pop(other_id, None)
            self.peer_last_roll.pop(other_id, None)

    def observe_peer_packet(self, other_id, other_state, other_zone, now_ms):
        """Records a decoded peer telemetry broadcast."""
        self.peer_states[other_id] = other_state
        self.peer_zones[other_id] = other_zone
        self.peer_last_seen[other_id] = now_ms
        if other_state == STATE_INFECTED:
            self.ever_saw_infected = True

    def expire_stale_peer(self, ch, now_ms):
        """Expires contact and state records for a peer channel that has gone silent."""
        if ch in self.peer_contact_start and now_ms - self.peer_last_seen.get(ch, now_ms) > PEER_CONTACT_TIMEOUT_MS:
            self.clear_peer_contact(ch)
        if ch in self.peer_states and now_ms - self.peer_last_seen.get(ch, now_ms) > PEER_STATE_TIMEOUT_MS:
            self.peer_states.pop(ch, None)
            self.peer_zones.pop(ch, None)
            self.peer_last_seen.pop(ch, None)

    def has_any_infected(self):
        """Returns True if this robot or any active peer is currently in STATE_INFECTED."""
        if self.sir_state == STATE_INFECTED:
            return True
        return any(state == STATE_INFECTED for state in self.peer_states.values())

    def is_finished(self, now_ms):
        """
        Returns True once at least one robot was infected during this run,
        no robot remains infected, and that condition holds for NO_INFECTED_END_MS.
        """
        if self.sir_state == STATE_INFECTED:
            self.ever_saw_infected = True
        if not self.ever_saw_infected or self.has_any_infected():
            self.no_infected_since = None
            return False

        if self.no_infected_since is None:
            self.no_infected_since = now_ms
            return False

        return (now_ms - self.no_infected_since) >= NO_INFECTED_END_MS

    def _should_roll_infection(self, other_id, now_ms):
        """Enforces one infection roll per INFECTION_CHECK_INTERVAL_MS after contact threshold."""
        last_roll = self.peer_last_roll.get(other_id)
        if last_roll is None:
            self.peer_last_roll[other_id] = now_ms
            return True
        if now_ms - last_roll >= INFECTION_CHECK_INTERVAL_MS:
            self.peer_last_roll[other_id] = last_roll + INFECTION_CHECK_INTERVAL_MS
            return True
        return False

    def check_zone_infection(self, now_ms):
        """
        Evaluates co-location with infected peers in the same valid zone.

        If this robot is susceptible and shares a valid zone with an infected peer for
        at least INFECTION_CONTACT_MS, rolls once per second with INFECTION_PROB_PER_SEC.
        Returns the infecting peer's ID if infection occurred, else None.
        """
        if self.sir_state != STATE_SUSCEPTIBLE or self.current_zone == ZONE_UNKNOWN:
            self.clear_peer_contact()
            return None

        for other_id, other_state in list(self.peer_states.items()):
            if now_ms - self.peer_last_seen.get(other_id, now_ms) > PEER_CONTACT_TIMEOUT_MS:
                self.clear_peer_contact(other_id)
                continue

            other_zone = self.peer_zones.get(other_id)
            if other_state == STATE_INFECTED and other_zone == self.current_zone:
                if other_id not in self.peer_contact_start:
                    self.peer_contact_start[other_id] = now_ms
                elif now_ms - self.peer_contact_start[other_id] >= INFECTION_CONTACT_MS:
                    if self._should_roll_infection(other_id, now_ms) and random.random() < INFECTION_PROB_PER_SEC:
                        self.sir_state = STATE_INFECTED
                        self.infected_since_ms = now_ms
                        self.ever_saw_infected = True
                        self.clear_peer_contact()
                        return other_id
            else:
                self.clear_peer_contact(other_id)

        return None

    def check_recovery(self, now_ms):
        """
        Transitions an infected robot to recovered once it has been infected
        for at least RECOVERY_DURATION_MS. Returns True if recovery occurred.
        """
        if self.sir_state != STATE_INFECTED:
            return False
        if self.infected_since_ms is None:
            self.infected_since_ms = now_ms
            return False
        if now_ms - self.infected_since_ms >= RECOVERY_DURATION_MS:
            self.sir_state = STATE_RECOVERED
            self.infected_since_ms = None
            return True
        return False
