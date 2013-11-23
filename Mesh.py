#!/usr/bin/python
#
#import inspect_shell
#

from random import seed
from sys import argv
from time import time
from traceback import format_exc

from PyQt4 import uic

from PyQt4.QtCore import Qt, QTimer

from PyQt4.QtGui import QApplication, QCursor, QIntValidator
from PyQt4.QtGui import QPushButton, QDesktopWidget, QLabel, QLineEdit, QMainWindow, QSlider

from MeshDevice import COLUMNS_DATA, START_TIME
from MeshDevice import TICKS_IN_SLOT, TICKS_IN_CYCLE, CYCLES_IN_SUPERCYCLE, CYCLES_IN_MINUTE, MINUTES_IN_HOUR, HOURS_IN_DAY
from MeshDevice import Device, timeFormat

from MeshView import DevicesModel, Column, ColumnAction, FONT_METRICS_CORRECTION

MAX_INT = 2 ** 31 - 1

SEED = 0

WINDOW_SIZE = 2.0 / 3
WINDOW_POSITION = (1 - WINDOW_SIZE) / 2

class SeedValidator(QIntValidator):
    def __init__(self, parent):
        QIntValidator.__init__(self, -MAX_INT - 1, MAX_INT, parent)

    def validate(self, inp, pos):
        return QIntValidator.validate(self, inp, pos) if str(inp).strip() else (self.Acceptable, pos)

class SeedLineEdit(QLineEdit):
    def configure(self):
        self.setText(str(SEED))
        self.setFixedWidth(self.fontMetrics().boundingRect(self.placeholderText()).width() * FONT_METRICS_CORRECTION)
        self.setValidator(SeedValidator(self))

class ResetButton(QPushButton):
    def configure(self):
        self.setFixedWidth(self.fontMetrics().boundingRect(self.text()).width() * (FONT_METRICS_CORRECTION + 0.3)) # Yes, it's a hack on a hack

class SpeedSlider(QSlider):
    minValue = None
    maxValue = None
    defaultValue = None
    speeds = None

    def configure(self, label, callback = None):
        self.label = label
        fontMetrics = self.label.fontMetrics()
        self.label.setMinimumWidth(max(fontMetrics.boundingRect(text).width() + 2 for (speed, text) in self.speeds)) # Yes, +2 is a hack
        self.callback = callback
        self.setMinimum(self.minValue)
        self.setMaximum(self.maxValue)
        self.setValue(self.defaultValue)
        self.valueChanged.connect(self.setValue)

    def setValue(self, value):
        QSlider.setValue(self, value)
        (self.speed, self.text) = self.speeds[value - self.minValue]
        self.label.setText(self.text)
        if self.callback:
            self.callback()

    def getSpeed(self):
        return self.speed

class TimeSpeedSlider(SpeedSlider):
    minValue = -13
    maxValue = 1
    defaultValue = 1 # ToDo 0
    speeds = tuple((1000 * 2 ** i / TICKS_IN_CYCLE, '1/%d' % 2 ** i) for i in xrange(-minValue, 0, -1)) + ((1, '1'),) + \
             tuple((1000.0 / 2 ** i / TICKS_IN_CYCLE, str(2 ** i)) for i in xrange(1, maxValue)) + ((0, 'max'),)

class MoveSpeedSlider(SpeedSlider):
    minValue = -7
    maxValue = 7
    defaultValue = 7 # ToDo 0
    speeds = ((0, 'stop'),) + \
             tuple((1.0 / 2 ** i, '1/%d' % 2 ** i) for i in xrange(-minValue - 1, 0, -1)) + \
             tuple((2 ** i, str(2 ** i)) for i in xrange(0, maxValue + 1))

class TimeLabel(QLabel):
    def configure(self):
        self.pittanceStyle = self.styleSheet()

    def setValue(self, value, pittance = False):
        self.setText(timeFormat(value))
        self.setStyleSheet(self.pittanceStyle if pittance else '')

class Mesh(QMainWindow):
    def __init__(self, *args, **kwargs):
        QMainWindow.__init__(self, *args, **kwargs)
        uic.loadUi('Mesh.ui', self)
        #Mesh.instance = self

    def configure(self):
        # Setting window size
        resolution = QDesktopWidget().screenGeometry()
        width = resolution.width()
        height = resolution.height()
        self.setGeometry(width * WINDOW_POSITION, height * WINDOW_POSITION, width * WINDOW_SIZE, height * WINDOW_SIZE)
        # Configuring widgets
        self.seedEdit.configure()
        self.seedEdit.returnPressed.connect(self.reset)
        self.resetButton.configure()
        self.resetButton.clicked.connect(self.reset)
        self.playButton.clicked.connect(self.play)
        self.playButton.setFocus()
        self.pauseButton.clicked.connect(self.pause)
        self.skipTickButton.clicked.connect(lambda: self.skip(1))
        self.skipSlotButton.clicked.connect(lambda: self.skip(TICKS_IN_SLOT))
        self.skipCycleButton.clicked.connect(lambda: self.skip(TICKS_IN_CYCLE))
        self.skipSuperCycleButton.clicked.connect(lambda: self.skip(TICKS_IN_CYCLE * CYCLES_IN_SUPERCYCLE))
        self.skipMinuteButton.clicked.connect(lambda: self.skip(TICKS_IN_CYCLE * CYCLES_IN_MINUTE))
        self.skipHourButton.clicked.connect(lambda: self.skip(TICKS_IN_CYCLE * CYCLES_IN_MINUTE * MINUTES_IN_HOUR))
        self.skipDayButton.clicked.connect(lambda: self.skip(TICKS_IN_CYCLE * CYCLES_IN_MINUTE * MINUTES_IN_HOUR * HOURS_IN_DAY))
        self.setRwS(self.rwsCheckBox.checkState())
        self.rwsCheckBox.stateChanged.connect(self.setRwS)
        self.playing = self.skippingTo = None # for TimeSpeedSlider callback
        self.timeSpeedSlider.configure(self.timeSpeedValueLabel, self.wait)
        self.moveSpeedSlider.configure(self.moveSpeedValueLabel)
        self.globalTimeValueLabel.configure()
        self.statusBar.hide()
        self.timer = QTimer(self)
        # Configure devices
        Device.configure(self.moveSpeedSlider.getSpeed, self)
        columns = tuple(Column(nColumn, *args) for (nColumn, args) in enumerate(COLUMNS_DATA))
        self.devicesModel = DevicesModel(Device.devices, columns, self)
        self.devicesTableView.configure(self.devicesModel, self.devicesMapFrame, self.deviceTableViewChangedSample)
        for column in columns:
            ColumnAction(column, self.devicesTableView.setColumnHidden, self.columnsMenu)
        self.devicesMapFrame.configure(Device.devices, lambda a, b: Device.relation(a, b).distance, self.devicesModel.getDeviceSelection, self.devicesTableView.selectDevice, self.activeDeviceVisualSample, self.inactiveDeviceVisualSample)
        for sample in (self.activeDeviceVisualSample, self.inactiveDeviceVisualSample, self.deviceTableViewChangedSample):
            sample.hide()
        # Starting up!
        self.playing = True # will be toggled immediately by pause()
        self.pause()
        self.reset()
        self.show()
        self.devicesMapFrame.afterShow() # must be performed after show()
        self.resize(self.width() + self.leftLayout.geometry().height() - self.devicesMapFrame.width(), self.height())

    def reset(self):
        text = str(self.seedEdit.text()).strip()
        seed(int(text) if text else None)
        self.time = START_TIME - 1 # will be +1 at the first tick
        for device in Device.devices:
            device.reset()
        self.tick(firstTick = True)

    def play(self):
        assert not self.playing
        self.playing = True
        self.skippingTo = None
        self.playButton.setEnabled(False)
        self.pauseButton.setEnabled(True)
        self.pauseButton.setFocus()
        self.wait(True, True)

    def _pause(self):
        self.timer.stop()
        self.playing = False
        self.pauseButton.setEnabled(False)
        self.playButton.setEnabled(True)

    def pause(self):
        assert self.playing
        self._pause()
        self.skippingTo = None
        self.playButton.setFocus()

    def skip(self, ticksToSkip):
        def addAndCut(what, by):
            return (what + by) // by * by
        self._pause()
        self.skippingTo = addAndCut(self.time, ticksToSkip)
        if self.redrawWhileSkipping:
            self.timer.singleShot(0, self.tick)
        else: # not redrawing
            if ticksToSkip > 1:
                QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            while self.time < self.skippingTo:
                self.tick()
            self.skippingTo = None
            self.devicesModel.refresh()
            self.devicesMapFrame.refresh()
            if ticksToSkip > 1:
                QApplication.restoreOverrideCursor()

    def setRwS(self, state):
        self.redrawWhileSkipping = bool(state)

    def wait(self, firstWait = False, start = False):
        if not self.playing:
            return
        now = time() * 1000
        if start:
            self.previousTickTime = now
            dt = self.timeSpeedSlider.speed
        else:
            dt = self.previousTickTime + self.timeSpeedSlider.speed - now
        if dt > 1:
            self.timer.singleShot(dt, self.wait)
        else:
            self.previousTickTime = now
            self.tick(firstWait)

    def tick(self, pittance = False, firstTick = False): # ToDo: avoid transmissions on first tick
        self.time += 1
        self.globalTimeValueLabel.setValue(self.time, pittance)
        Device.fullTick()
        if self.playing or self.redrawWhileSkipping or firstTick:
            self.devicesModel.refresh(firstTick)
            self.devicesMapFrame.refresh()
        if self.playing:
            self.timer.singleShot(0, lambda: self.wait(True))
        elif self.redrawWhileSkipping:
            if self.time < self.skippingTo: # redrawWhileSkipping
                self.timer.singleShot(0, self.tick)
            else: # done skipping
                self.skippingTo = None

def main():
    try:
        application = QApplication(argv)
        Mesh().configure()
        return application.exec_()
    except KeyboardInterrupt:
        pass
    except BaseException:
        print format_exc()

if __name__ == '__main__':
    main()
