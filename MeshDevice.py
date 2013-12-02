#!/usr/bin/python
from logging import getLogger, getLoggerClass, DEBUG
from math import ceil, cos, exp, log, log10, pi, sin, sqrt
from random import gauss, random

INF = float('inf')

NUM_DEVICES = 20 # ToDo
NUM_STATIC_DEVICES = 10

TICKS_IN_SLOT = 10
TICKS_IN_PACKET = 8
SLOTS_IN_CYCLE = NUM_DEVICES
CYCLES_IN_SUPERCYCLE = 4
CYCLES_IN_MINUTE = 100
MINUTES_IN_HOUR = 100
HOURS_IN_DAY = 100

TICKS_IN_CYCLE = TICKS_IN_SLOT * SLOTS_IN_CYCLE

TICKS_IN_SUPERCYCLE = TICKS_IN_CYCLE * CYCLES_IN_SUPERCYCLE

TIME_ASPECTS = (TICKS_IN_SLOT, SLOTS_IN_CYCLE, CYCLES_IN_MINUTE, MINUTES_IN_HOUR, HOURS_IN_DAY)

TIME_LOGS = tuple((aspect, int(ceil(log10(aspect)))) for aspect in TIME_ASPECTS)

START_TIME = reduce(lambda x, y: x * y, TIME_ASPECTS) # 1 day

MAP_SIZE = 100

MIN_CHANCE = 0.01
HEARING_RADIUS = 0.1 * MAP_SIZE # Chance of reception after TICKS_IN_PACKET ticks is MIN_CHANCE at this radius and 0.5 at 0.388 of this radius
HEARING_CONSTANT = -TICKS_IN_PACKET * HEARING_RADIUS ** 2 / log(MIN_CHANCE)

MAX_SPEED = float(HEARING_RADIUS) / 2 / TICKS_IN_CYCLE # It should take 2 cycles to move through reasonable range (2*(R/2) = R), e. g. 36 km/h = 10 m/s => R = 20m

LISTEN = 'LISTEN'
NOISE = 'NOISE'
NOISE_BEFORE = 'NOISE_BEFORE'
PROBE = 'PROBE'
PROBE_AFTER = 'PROBE_AFTER'
OK = 'OK'

PROBES = (PROBE, PROBE_AFTER)

LISTENING = (LISTEN,) + PROBES

def timeFormat(value):
    remainder = value % 1
    value = int(value)
    aspects = []
    for (aspect, timeLog) in TIME_LOGS:
        aspects.append('%%0%dd' % timeLog % (value % aspect))
        value //= aspect
    aspects.append(str(value))
    return ':'.join(reversed(aspects)) + (('.%d' % (remainder * 10)) if remainder else '')

def effectiveGauss(m = 0, limit = 1):
    return min(max(gauss(m, limit / 3), m - limit), m + limit)

COLUMNS_DATA = (
    (True, False, 'ID', 'Device ID', 'number', NUM_DEVICES),
    (True, False, 'Moving', None, 'isMoving', True, None, lambda x: 'yes' if x else 'no'),
    (True, True, 'Time speed', 'Local time speed deviation', 'timeSpeed', 1, '%+.1f%%', lambda x: (x - 1) * 100),
    (True, True, 'Time', 'Local time', 'time', START_TIME + 0.1, None, timeFormat),
    (True, True, 'X', None, 'x', MAP_SIZE, '%.1f'),
    (True, True, 'Y', None, 'y', MAP_SIZE, '%.1f'),
    (True, True, 'Direction', None, 'direction', pi, '%.0f', lambda x: -x * 180 / pi),
    (True, True, 'Speed', None, 'moveSpeed', MAX_SPEED, '%.1f', lambda x: x * TICKS_IN_CYCLE),
    (True, True, 'DtT', 'Distance to target', 'distanceToTarget', MAP_SIZE, '%.1f'),
)

class CheckerLogger(getLoggerClass()):
    checker = None

    def configure(self, checker):
        self.checker = checker

    def _log(self, level, message, *args, **kwargs):
        assert self.checker
        prefix = self.checker(level)
        if prefix:
            super(CheckerLogger, self)._log(level, "%s%s" % (prefix, message), *args, **kwargs)

class Device(object): # pylint: disable=R0902
    def __init__(self, number, parent):
        assert number in xrange(0, NUM_DEVICES)
        self.number = number
        self.name = ('Device#%%0%dd' % len(str(NUM_DEVICES - 1))) % number
        self.parent = parent
        self.isMoving = number >= NUM_STATIC_DEVICES
        self.logger = getLogger(self.name)
        self.logger.configure(self.logChecker) # pylint: disable=E1103
        self.watched = None
        self.reset()

    @classmethod
    def configure(cls, getSpeed, parent):
        cls.loggingLevel = DEBUG
        cls.getSpeed = getSpeed
        cls.getGlobalTime = parent.getTime
        cls.devices = tuple(cls(i, parent) for i in xrange(0, NUM_DEVICES))
        cls.relations = tuple([None,] * NUM_DEVICES for _ in xrange(NUM_DEVICES))
        for i in xrange(NUM_DEVICES):
            for j in xrange(i + 1, NUM_DEVICES):
                cls.relations[i][j] = cls.relations[j][i] = DeviceRelation(cls.devices[i], cls.devices[j])

    @classmethod
    def relation(cls, a, b):
        return cls.relations[a.number][b.number]

    @classmethod
    def fullTick(cls):
        for device in cls.devices: # move time, move devices
            device.move()
        for i in xrange(NUM_DEVICES): # calculate distances
            for j in xrange(i + 1, NUM_DEVICES):
                cls.relations[i][j].update()
        for device in cls.devices: # prepare to transmission
            device.prepare()
        for device in cls.devices: # handle transmissions
            device.processTX()
        for device in cls.devices: # process transmissions
            device.checkChannel()
        for device in cls.devices: # deliver transmissions
            device.processRX()

    def logChecker(self, level):
        return "%s  %s  %s  %d%%  " % (timeFormat(self.getGlobalTime()), self.name, timeFormat(self.time), self.powerUsage * 100) if self.watched and level >= self.loggingLevel else None

    def setWatched(self, watched = True):
        if self.watched is None and not watched:
            return
        self.watched = True
        self.logger.debug("ON" if watched else "OFF")
        self.watched = watched

    def reset(self):
        self.timeSpeed = 1.0 # effectiveGauss(1, 0.1) # ToDo
        self.time = START_TIME - self.timeSpeed # START_TIME * effectiveGauss(1, 0.9) - self.timeSpeed
        self.timeToTarget = None
        self.x = MAP_SIZE * random()
        self.y = MAP_SIZE * random()
        self.cycleToReceive = 0
        self.txPacket = self.rxPacket = self.oldTxPacket = self.rxCounter = self.rxChannel = None
        self.txCount = self.rxCount = self.tickCount = self.powerUsage = 0
        self.setTarget()

    def setTarget(self):
        if self.isMoving:
            self.direction = (random() * 2 - 1) * pi # [-pi, pi)
            self.sinD = sin(self.direction)
            self.cosD = cos(self.direction)
            distX = float(MAP_SIZE - self.x if self.cosD > 0 else -self.x) / self.cosD if self.cosD else INF
            distY = float(MAP_SIZE - self.y if self.sinD > 0 else -self.y) / self.sinD if self.sinD else INF
            self.distanceToTarget = min(distX, distY) * effectiveGauss(0.55, 0.45)
            self.moveSpeed = random() * MAX_SPEED
        else:
            self.direction = self.sinD = self.cosD = self.distanceToTarget = self.moveSpeed = None

    def move(self):
        self.time += self.timeSpeed
        (self.nSlot, self.nTickInSlot) = divmod(int(self.time), TICKS_IN_SLOT)
        if self.isMoving:
            move = self.moveSpeed * self.getSpeed()
            self.x = max(0, min(MAP_SIZE, self.x + move * self.cosD))
            self.y = max(0, min(MAP_SIZE, self.y + move * self.sinD))
            self.distanceToTarget -= move
            if self.distanceToTarget < 0:
                self.setTarget()

    def transmitting(self):
        return self.txPacket and not self.listening()

    def listening(self):
        return self.txPacket in LISTENING

    def checkChannel(self):
        reachableRelations = (r for r in self.relations[self.number] if r and r.chance)
        reachableDevices = (r.other(self) for r in reachableRelations if random() < r.chance)
        heardDevices = tuple(d for d in reachableDevices if d.transmitting()) # ToDo: Make all this info visible in logging
        self.rxChannel = (heardDevices[0].txPacket if len(heardDevices) == 1 else NOISE) if heardDevices else None

    def processTX(self):
        if self.nTickInSlot == 0: # If 0 gets skipped because of uneven time speed, transmission will be skipped.
            if self.rxPacket:
                pass # if we're receiving, continue receiving, do not transmit
            else:
                self.txPacket = self.tx() or None # start transmission, make sure it's not empty string or something else False
                if self.rxChannel: # if something was in channel on previous tick
                    self.txPacket = NOISE_BEFORE
        elif self.nTickInSlot == TICKS_IN_PACKET and self.transmitting():
            self.txPacket = PROBE_AFTER # cease transmission
        if self.transmitting():
            self.txCount += 1 # calculate power consumption
        elif self.listening():
            self.rxCount += 1
        self.tickCount += 1
        self.powerUsage = float(self.txCount + self.rxCount) / self.tickCount
        if self.txPacket != self.oldTxPacket:
            self.oldTxPacket = self.txPacket
            self.logger.info("TX: %s" % self.txPacket) # ToDo: improve filtering, make this debug, move logical logging to TestDevice?

    def processRX(self):
        if not self.listening():
            pass
        elif self.txPacket is NOISE_BEFORE:
            self.txPacket = None
            self.doRX(NOISE_BEFORE)
        elif self.txPacket in PROBES:
            self.txPacket = None
            self.doRX(NOISE if self.rxChannel else OK)
        elif not self.rxChannel: # channel seems quiet
            if self.rxPacket:
                self.doRX(NOISE)
        elif self.rxChannel is NOISE:
            self.doRX(NOISE)
        elif self.rxChannel is self.rxPacket: # continuing receiving the same packet
            if self.rxCounter < TICKS_IN_PACKET - 1:
                self.rxCounter += 1 # continuing receiving
            else:
                self.doRX(self.rxPacket) # complete receving
        else: # there's a transmission but of a different packet
            self.rxPacket = self.rxChannel
            self.rxCounter = 1

    def doRX(self, what):
        assert what
        self.rxPacket = self.rxCounter = None
        self.logger.info("RX: %s" % what)
        self.rx(what)

    def prepare(self):
        '''Device logic function, called at the beginning of a tick.
           Should make preparations usable for both tx() and rx().'''
        pass

    def tx(self):
        '''Device logic function, called after prepare().
           Should return a packet to transmit,
           or LISTEN to listen for incoming transmissions,
           or PROBE to check if channel is busy,
           or None if nothing is to be done.'''
        pass

    def rx(self, rxPacket):
        '''Device logic function, called after prepare() and tx().
           rxPacket is either a complete received packet,
           or NOISE_BEFORE if a transmission was cancelled because the channel was busy,
           or NOISE if probe was issued or transmission was successful but channel was found busy afterwards,
           or OK if probe was issued or transmission was successful and channel was found clear afterwards.'''
        pass

class DeviceRelation(object):
    def __init__(self, a, b):
        assert a is not b
        self.a = a
        self.b = b
        self.update()

    def update(self): # pylint: disable=E0202
        self.distance = sqrt((self.a.x - self.b.x) ** 2 + (self.a.y - self.b.y) ** 2)
        self.chance = exp(-(self.distance ** 2 / HEARING_CONSTANT)) if self.distance <= HEARING_RADIUS else None

    def other(self, what):
        return self.b if what is self.a else self.a if what is self.b else None
