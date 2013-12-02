#!/usr/bin/python
from random import randint

from MeshDevice import Device
from MeshDevice import LISTEN, NOISE
from MeshDevice import SLOTS_IN_CYCLE, CYCLES_IN_SUPERCYCLE

class TestDevice(Device):
    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)
        self.prevousSlotInCycle = None

    def prepare(self): # ToDo: Is it needed for rx? If not, move it to tx?
        '''Device logic function, called at the beginning of a tick.'''
        (self.nCycle, self.nSlotInCycle) = divmod(self.nSlot, SLOTS_IN_CYCLE)
        self.nCycleInSupercycle = self.nCycle % CYCLES_IN_SUPERCYCLE
        if self.nCycleInSupercycle == 0 and self.nSlotInCycle == 0 and self.prevousSlotInCycle != 0:
            self.cycleToReceive = randint(0, CYCLES_IN_SUPERCYCLE - 1)
        self.prevousSlotInCycle = self.nSlotInCycle

    def tx(self):
        '''Device logic function, called after prepare().
           Should return a packet to transmit,
           or LISTEN to listen for incoming transmissions,
           or None if nothing is to be done.'''
        if self.nCycleInSupercycle == self.cycleToReceive:
            return LISTEN # listening cycle
        if self.nSlotInCycle != self.number: # ToDo: also skip transmission if channel was busy after previous transmission
            return None  # not our slot
         # Transmit!
        return self.createPacket()

    def rx(self, rxPacket):
        '''Device logic function, called after prepare() and tx()
           if there was an incoming transmission.
           rxPacket is either a complete received packet or NOISE.'''
        assert rxPacket
        if rxPacket is NOISE:
            # ToDo: if this is after transmission, do not transmit for a supercycle?
            return
        return '#%d < %s' % (self.number, rxPacket)

    def createPacket(self):
        return '#%d OK' % self.number
