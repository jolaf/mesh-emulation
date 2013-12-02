#!/usr/bin/python
from random import randint

from MeshDevice import Device
from MeshDevice import LISTEN, NOISE, NOISE_BEFORE, OK
from MeshDevice import SLOTS_IN_CYCLE, CYCLES_IN_SUPERCYCLE

class TestDevice(Device):
    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)
        self.prevousSlotInCycle = None
        self.skipTransmissions = None

    def prepare(self):
        '''Device logic function, called at the beginning of a tick.
           Should make preparations usable for both tx() and rx().'''
        (self.nCycle, self.nSlotInCycle) = divmod(self.nSlot, SLOTS_IN_CYCLE)
        self.nCycleInSupercycle = self.nCycle % CYCLES_IN_SUPERCYCLE
        if self.nCycleInSupercycle == 0 and self.nSlotInCycle == 0 and self.prevousSlotInCycle != 0:
            self.cycleToReceive = randint(0, CYCLES_IN_SUPERCYCLE - 1)
        self.prevousSlotInCycle = self.nSlotInCycle

    def tx(self):
        '''Device logic function, called after prepare().
           Should return a packet to transmit,
           or LISTEN to listen for incoming transmissions,
           or PROBE to check if channel is busy,
           or None if nothing is to be done.'''
        if self.nCycleInSupercycle == self.cycleToReceive:
            self.skipTransmissions = False
            return LISTEN # listening cycle
        if self.nSlotInCycle != self.number: # not our transmission slot
            return None
        return '#%d OK' % self.number # ToDo: include real packet content here

    def rx(self, rxPacket):
        '''Device logic function, called after prepare() and tx().
           rxPacket is either a complete received packet,
           or NOISE_BEFORE if a transmission was cancelled because the channel was busy,
           or NOISE if probe was issued or transmission was successful but channel was found busy afterwards,
           or OK if probe was issued or transmission was successful and channel was found clear afterwards.'''
        if rxPacket is NOISE_BEFORE: # transmission was cancelled because channel was busy
            pass # there's nothing we can do, except to wait for a listening cycle and listen
        elif rxPacket is NOISE: # we never use PROBE, which means this is noise after successful transmission
            self.skipTransmissions = True # skip transmissions until next listening cycle
        elif rxPacket is OK:
            pass # we're just happy!
        else:
            pass # ToDo: include real incoming packet processing facilities
