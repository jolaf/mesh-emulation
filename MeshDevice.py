#!/usr/bin/python
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

TIME_ASPECTS = (TICKS_IN_SLOT, SLOTS_IN_CYCLE, CYCLES_IN_MINUTE, MINUTES_IN_HOUR, HOURS_IN_DAY)

TIME_LOGS = tuple((aspect, int(ceil(log10(aspect)))) for aspect in TIME_ASPECTS)

START_TIME = reduce(lambda x, y: x * y, TIME_ASPECTS) # 1 day

MAP_SIZE = 100

HEARING_RADIUS = 0.1 * MAP_SIZE # chance of reception after TICKS_IN_PACKET ticks is 0.5 at 0.388 of this radius
MIN_CHANCE = 0.01
HEARING_CONSTANT = -TICKS_IN_PACKET * HEARING_RADIUS ** 2 / log(MIN_CHANCE)

FASTEST_GOER = 10
MAX_SPEED = float(MAP_SIZE) / FASTEST_GOER / TICKS_IN_CYCLE

NOISE = 'NOISE'
LISTEN = 'LISTEN'
PROBE = 'PROBE'

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

class Device(object): # pylint: disable=R0902
    def __init__(self, number, parent):
        assert number in xrange(1, NUM_DEVICES + 1)
        self.number = number
        self.parent = parent
        self.isMoving = number > NUM_STATIC_DEVICES
        self.txPacket = self.rxPacket = self.rxCounter = None
        self.reset()

    @classmethod
    def configure(cls, getSpeed, parent):
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
        for i in xrange(NUM_DEVICES):
            for j in xrange(i + 1, NUM_DEVICES):
                cls.relations[i][j].update()
        for device in cls.devices: # handle transmissions
            device.processTX()
        for device in cls.devices: # deliver transmissions
            device.processRX()

    def reset(self):
        self.timeSpeed = effectiveGauss(1, 0.1)
        self.time = START_TIME * effectiveGauss(1, 0.9) - self.timeSpeed
        self.timeToTarget = None
        self.x = MAP_SIZE * random()
        self.y = MAP_SIZE * random()
        self.cycleToReceive = 0
        self.channelBusy = None
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

    def processTX(self):
        self.prepare()
        if self.nTickInSlot == 0: # ToDo: what if 0 gets skipped because of uneven time speed?
            self.txPacket = self.tx() # start transmission
        elif self.nTickInSlot == TICKS_IN_PACKET and self.txPacket is not LISTEN:
            self.txPacket = None # cease transmission

    def processRX(self):
        packet = None
        if self.txPacket is LISTEN: # ToDo: and if not?
            reachableDevices = (r.other(self) for r in self.relations[self.number - 1] if r and r.chance and random() < r.chance)
            heardDevices = tuple(d for d in reachableDevices if d.txPacket not in (None, LISTEN))
            if heardDevices:
                packet = heardDevices[0].txPacket if len(heardDevices) == 1 else NOISE
        if packet is None: # channel seems quiet
            if self.rxPacket:
                self.rxPacket = self.rxCounter = None
                self.rx(NOISE) # ToDo: should not happen if we're not listening
        elif packet is NOISE: # noise in the channel
            self.rxPacket = self.rxCounter = None
            self.rx(NOISE)
        elif packet is self.rxPacket: # continuing receiving the same packet
            if self.rxCounter < TICKS_IN_PACKET - 1:
                self.rxCounter += 1
            else:
                self.rxPacket = self.rxCounter = None
                self.rx(packet)
        else: # there's a transmission but of a different packet
            self.rxPacket = packet
            self.rxCounter = 1
            self.rx(NOISE)

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
        assert self.nTickInSlot == 0
        if self.channelBusy: # ToDo: where this value is set?
            self.channelBusy = None
            return LISTEN
        elif self.nCycleInSupercycle == self.cycleToReceive:
            return LISTEN # listening cycle
        elif self.nSlotInCycle == (self.number - 2) % NUM_DEVICES:
            return PROBE # probe channel before transmitting
        elif self.nSlotInCycle != self.number - 1:
            return None  # not our slot
        else:
            return self.createPacket() # transmit!

    def rx(self, rxPacket):
        '''Device logic function, called after prepare() and tx()
           if there was an incoming transmission.
           rxPacket is either a complete received packet or NOISE.'''
        assert rxPacket
        #assert self.nTickInSlot == 0 # ToDo: seems not true
        if rxPacket is NOISE: # ToDo: make sure it only happens once per slot
            self.channelBusy = True
        else:
            print self.number, rxPacket

    def createPacket(self):
        #print '#%d' % self.number
        return '#%d' % self.number

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
        return self.b is what is self.a else self.a if what is self.b else None
