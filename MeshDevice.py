#!/usr/bin/python
from logging import getLogger, getLoggerClass, DEBUG
from math import ceil, cos, exp, log, log10, pi, sin, sqrt
from random import gauss, random, randint

INF = float('inf')

NUM_DEVICES = 100
NUM_STATIC_DEVICES = 9

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

HEARING_RADIUS = 0.1 * MAP_SIZE # chance of reception after TICKS_IN_PACKET ticks is 0.5 at 0.388 of this radius
MIN_CHANCE = 0.01
HEARING_CONSTANT = -TICKS_IN_PACKET * HEARING_RADIUS ** 2 / log(MIN_CHANCE)

FASTEST_GOER = 10 # ToDo: Adjust, it should take 2 cycles to move through range, 36 km/h = 10 m/s = 1/2 R, R = 20m
MAX_SPEED = float(MAP_SIZE) / FASTEST_GOER / TICKS_IN_CYCLE

NOISE = 'NOISE'
LISTEN = 'LISTEN'
PROBE = 'PROBE'

LISTENING = (LISTEN, PROBE)
SILENT = LISTENING + (None,)

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

    def _log(self, level, *args, **kwargs):
        if not self.checker or self.checker(level):
            super(CheckerLogger, self)._log(level, *args, **kwargs)

class Device(object): # pylint: disable=R0902
    def __init__(self, number, parent):
        assert number in xrange(1, NUM_DEVICES + 1)
        self.number = number
        self.parent = parent
        self.isMoving = number > NUM_STATIC_DEVICES
        self.logger = getLogger('Device#%d' % number)
        self.logger.configure(self.logChecker) # pylint: disable=E1103
        self.watched = None
        self.reset()

    @classmethod
    def configure(cls, getSpeed, parent):
        cls.loggingLevel = DEBUG
        cls.getSpeed = getSpeed
        cls.devices = tuple(Device(i, parent) for i in xrange(1, NUM_DEVICES + 1))
        cls.relations = tuple([None,] * NUM_DEVICES for _ in xrange(NUM_DEVICES))
        for i in xrange(NUM_DEVICES):
            for j in xrange(i + 1, NUM_DEVICES):
                cls.relations[i][j] = cls.relations[j][i] = DeviceRelation(cls.devices[i], cls.devices[j])

    @classmethod
    def relation(cls, a, b):
        return cls.relations[a.number - 1][b.number - 1]

    @classmethod
    def fullTick(cls):
        for device in cls.devices: # move time, move devices
            device.tick()
        for i in xrange(NUM_DEVICES): # calculate distances
            for j in xrange(i + 1, NUM_DEVICES):
                cls.relations[i][j].update()
        for device in cls.devices: # prepare devices
            device.prepare()
        for device in cls.devices: # handle transmissions
            device.processTX()
        for device in cls.devices: # process transmissions
            device.checkChannel()
        for device in cls.devices: # deliver transmissions
            device.processRX()

    def logChecker(self, level):
        return self.watched and level >= self.loggingLevel

    def setWatched(self, watched = True):
        if self.watched is None and not watched:
            return
        self.watched = True
        self.logger.debug('ON' if watched else 'OFF')
        self.watched = watched

    def reset(self):
        self.timeSpeed = effectiveGauss(1, 0.1)
        self.time = START_TIME * effectiveGauss(1, 0.9) - self.timeSpeed
        self.timeToTarget = None
        self.x = MAP_SIZE * random()
        self.y = MAP_SIZE * random()
        self.cycleToReceive = 0
        self.txPacket = self.rxPacket = self.rxCounter = self.rxChannel = None
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

    def tick(self):
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
        return self.txPacket not in SILENT

    def listening(self):
        return self.txPacket in LISTENING

    def checkChannel(self):
        reachableRelations = (r for r in self.relations[self.number - 1] if r and r.chance)
        reachableDevices = (r.other(self) for r in reachableRelations if random() < r.chance)
        heardDevices = tuple(d for d in reachableDevices if d.transmitting())
        self.rxChannel = (heardDevices[0].txPacket if len(heardDevices) == 1 else NOISE) if heardDevices else None

    def processTX(self):
        if self.nTickInSlot == 0: # ToDo: what if 0 gets skipped because of uneven time speed?
            if not self.rxPacket: # If we're listening, continue receiving
                if self.rxChannel:
                    self.txPacket = PROBE # probing before transmission # ToDo: or just None?
                else:
                    self.txPacket = self.tx() or None # start transmission, make sure it's not empty string or something
                    self.logger.info('TX:%s', self.txPacket)
        elif self.nTickInSlot == TICKS_IN_PACKET and self.transmitting():
            self.txPacket = PROBE # cease transmission
        if self.transmitting():
            self.txCount += 1 # calculate power consumption
        elif self.listening():
            self.rxCount += 1
        self.tickCount += 1
        self.powerUsage = float(self.txCount + self.rxCount) / self.tickCount

    def processRX(self):
        if not self.listening():
            return
        if self.txPacket is PROBE:
            self.txPacket = None
            if self.rxChannel:
                self.doRX(NOISE)
            return
        if not self.rxChannel: # channel seems quiet
            if self.rxPacket:
                self.doRX(NOISE, True)
        elif self.rxChannel is NOISE:
            self.doRX(NOISE, True)
        elif self.rxChannel is self.rxPacket: # continuing receiving the same packet
            if self.rxCounter < TICKS_IN_PACKET - 1:
                self.rxCounter += 1 # continuing receiving
            else:
                self.doRX(self.rxChannel, True) # complete receving
        else: # there's a transmission but of a different packet
            self.rxPacket = self.rxChannel
            self.rxCounter = 1

    def doRX(self, what, reset = False):
        if reset:
            self.rxPacket = self.rxCounter = None
        self.logger.info('RX:%s', what)
        self.rx(what)

    def prepare(self): # ToDo: Is it needed for rx? If not, move it to tx?
        '''Device logic function, called at the beginning of a tick.'''
        (self.nCycle, self.nSlotInCycle) = divmod(self.nSlot, SLOTS_IN_CYCLE)
        self.nCycleInSupercycle = self.nCycle % CYCLES_IN_SUPERCYCLE
        if self.nCycleInSupercycle == 0:
            self.cycleToReceive = randint(0, CYCLES_IN_SUPERCYCLE - 1)

    def tx(self):
        '''Device logic function, called after prepare().
           Should return a packet to transmit,
           or LISTEN to listen for incoming transmissions,
           or None if nothing is to be done.'''
        if self.nCycleInSupercycle == self.cycleToReceive:
            return LISTEN # listening cycle
        if self.nSlotInCycle != self.number - 1: # ToDo: also skip transmission if channel was busy after previous transmission
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
        return '#%d >' % self.number

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
