#!/usr/bin/python
from random import randint

from MeshDevice import Device, timeFormat
from MeshDevice import LISTEN, NOISE, NOISE_BEFORE, OK
from MeshDevice import NUM_DEVICES, TIME_TTL
from MeshDevice import TICKS_IN_SLOT, TICKS_IN_PACKET, SLOTS_IN_CYCLE, CYCLES_IN_SUPERCYCLE

class Packet(object):
    def __init__(self, device):
        self.sender = device.number
        self.nCycle = device.nCycle
        self.timeAuthor = device.timeAuthor
        self.timeAge = device.timeAge

    def __str__(self):
        return "#%d%s/%s" % (self.sender, ('(%d:%d)' % (self.timeAuthor, self.timeAge)) if self.timeAuthor != None else '', self.nCycle)

class TestDevice(Device):
    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)
        self.previousSlotInCycle = None
        self.skipTransmissions = None
        self.timeAuthor = self.timeAge = None
        self.states = [None,] * NUM_DEVICES

    def getStringTime(self):
        return Device.getStringTime() + (' (%d:%d)' % (self.timeAuthor, self.timeAge)) if self.timeAuthor != None else ''

    def adjustTime(self, packet):
        if packet:
            if packet.timeAuthor != None:
                self.timeAuthor = packet.timeAuthor
                self.timeAge = packet.timeAge
            else:
                self.timeAuthor = packet.sender
                self.timeAge = 0
            newTime = (packet.nCycle * SLOTS_IN_CYCLE + packet.sender) * TICKS_IN_SLOT + TICKS_IN_PACKET - 1 # ToDo: layers separation breach, fix!
        else:
            newTime = self.timeAuthor = self.timeAge = None
        self.logger.info("Adjusting time to %s" % (('(%d:%d) %s' % (self.timeAuthor, self.timeAge, timeFormat(newTime))) if newTime else 'self'))
        if newTime:
            self.time = newTime

    def prepare(self):
        '''Device logic function, called at the beginning of a tick.
           Should make preparations usable for both tx() and rx().
           Basic input parameter is device local time as self.nSlot.'''
        (self.nCycle, self.nSlotInCycle) = divmod(self.nSlot, SLOTS_IN_CYCLE)
        self.nCycleInSupercycle = self.nCycle % CYCLES_IN_SUPERCYCLE
        if self.previousSlotInCycle != self.nSlotInCycle:
            if self.nCycleInSupercycle == 0 and self.nSlotInCycle == 0:
                self.cycleToReceive = randint(0, CYCLES_IN_SUPERCYCLE - 1)
            if self.timeAuthor != None:
                if self.timeAge < TIME_TTL:
                    self.timeAge += 1
                else:
                    self.adjustTime(None)
        self.previousSlotInCycle = self.nSlotInCycle

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
        return Packet(self)

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
            assert rxPacket.__class__ is Packet
            remoteAuthor = rxPacket.timeAuthor if rxPacket.timeAuthor != None else rxPacket.sender
            localAuthor = self.timeAuthor if self.timeAuthor != None else self.number
            if (remoteAuthor, rxPacket.timeAge) < (localAuthor, self.timeAge):
                self.adjustTime(rxPacket)
            self.states[rxPacket.sender] = self.nCycle
