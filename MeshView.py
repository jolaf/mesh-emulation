#!/usr/bin/python
from PyQt4.QtCore import Qt, QAbstractTableModel, QLineF, QVariant
from PyQt4.QtGui import QAction, QColor, QGraphicsScene, QGraphicsView, QLabel, QPalette, QPixmap, QStyle
from PyQt4.QtGui import QItemDelegate, QItemSelection, QItemSelectionModel, QSortFilterProxyModel, QTableView

from MeshDevice import MAP_SIZE

FONT_METRICS_CORRECTION = 1.3

MAP_FIELD = 2
MAP_TOTAL = MAP_SIZE + 2 * MAP_FIELD

INVALID_DATA = QVariant()

RAW_ROLE = Qt.UserRole
CHANGED_ROLE = Qt.UserRole + 1

class Column(object):
    def __init__(self, number, checked, changing, name, description, fieldName, longestValue = 100, fmt = None, formatter = None):
        self.number = number
        self.checked = checked
        self.changing = changing
        self.name = name
        self.description = description
        self.fieldName = fieldName
        self.fmt = fmt
        self.formatter = formatter
        self.longestValue = self.process(longestValue)
        self.headers = { # This really is a part of View, but moving it off here doesn't work well
            Qt.DisplayRole: name,
            Qt.ToolTipRole: description or name,
            Qt.StatusTipRole: description or name,
            Qt.TextAlignmentRole: Qt.AlignRight
        }

    def process(self, data):
        if data is None:
            return None
        if self.formatter:
            data = self.formatter(data)
        return self.fmt % data if self.fmt else str(data)

class ColumnAction(QAction):
    def __init__(self, column, toggleCallback, menu):
        QAction.__init__(self, menu)
        self.setCheckable(True)
        self.setChecked(column.checked)
        self.setToolTip(column.description or column.name)
        self.setStatusTip(column.description or column.name)
        toggle = lambda checked: toggleCallback(column.number, not checked)
        toggle(column.checked)
        self.toggled.connect(toggle)

class Cell(dict):
    def __init__(self, device, column):
        dict.__init__(self)
        self[CHANGED_ROLE] = None
        self[RAW_ROLE] = None
        self[Qt.DisplayRole] = ''
        self.device = device
        self.column = column

    def setData(self, initial = False):
        data = getattr(self.device, self.column.fieldName)
        if data == self[RAW_ROLE]:
            self[CHANGED_ROLE] = False
        else:
            self[CHANGED_ROLE] = not initial
            self[RAW_ROLE] = data
            self[Qt.DisplayRole] = self.column.process(data)

    def getData(self, role):
        data = self.get(role)
        return data if data != None else self.column.headers.get(role, INVALID_DATA)

class DevicesModel(QAbstractTableModel):
    def __init__(self, devices, columns, parent):
        QAbstractTableModel.__init__(self, parent)
        self.columns = columns
        self.cache = tuple(tuple(Cell(device, column) for column in columns) for device in devices)
        self.numRows = len(devices)
        self.numColumns = len(columns)
        self.minIndex = self.createIndex(0, 0)
        self.maxIndex = self.createIndex(self.numRows - 1, self.numColumns - 1)

    def rowCount(self, _parent = None):
        return self.numRows

    def columnCount(self, _parent = None):
        return self.numColumns

    def getDeviceSelection(self, nRow):
        return QItemSelection(self.index(nRow, 0), self.index(nRow, self.columnCount() - 1))

    def headerData(self, section, orientation, role = Qt.DisplayRole):
        try:
            return self.columns[section].headers[role] if orientation == Qt.Horizontal else section
        except LookupError: pass # ToDo: avoid exceptions
        except ValueError: pass
        return INVALID_DATA

    def data(self, index, role = Qt.DisplayRole):
        try:
            return self.cache[index.row()][index.column()].getData(role)
        except LookupError: pass
        except AttributeError: pass
        return INVALID_DATA

    def refresh(self, initial = False):
        for cacheRow in self.cache:
            for cell in cacheRow:
                cell.setData(initial)
        self.dataChanged.emit(self.minIndex, self.maxIndex)

class RoleDefaultSortProxyModel(QSortFilterProxyModel):
    def __init__(self, sourceModel, role = Qt.DisplayRole, parent = None):
        QSortFilterProxyModel.__init__(self, parent)
        self.role = role
        self.setSourceModel(sourceModel)
        self.setDynamicSortFilter(True)

    def lessThan(self, left, right):
        leftData = self.sourceModel().data(left, self.role)
        rightData = self.sourceModel().data(right, self.role)
        return leftData < rightData if leftData != rightData else left.row() < right.row()

class DevicesTableDelegate(QItemDelegate): # QStyledItemDelegate doesn't handle selection background color properly
    def __init__(self, inactivePalette, activePalette, parent):
        QItemDelegate.__init__(self, parent)
        self.inactivePalette = inactivePalette
        self.activePalette = activePalette

    def paint(self, paint, option, index):
        option.palette = self.activePalette if index.data(CHANGED_ROLE).toBool() else self.inactivePalette
        QItemDelegate.paint(self, paint, option, index)

    def drawFocus(self, painter, option, rect):
        option.state &= ~QStyle.State_HasFocus
        QItemDelegate.drawFocus(self, painter, option, rect)

class DevicesTableView(QTableView):
    def configure(self, devicesModel, devicesGraphicsView, changedDataSample):
        self.devicesGraphicsView = devicesGraphicsView
        self.setModel(RoleDefaultSortProxyModel(devicesModel, RAW_ROLE))
        self.columnWidths = tuple(self.fontMetrics().boundingRect(column.longestValue).width() * FONT_METRICS_CORRECTION for column in devicesModel.columns)
        #for column in devicesModel.columns: # ToDo: Works for width but not for height, find current row height?
        #    column.headers[Qt.SizeHintRole] = QSize(self.fontMetrics().boundingRect(column.longestValue).size().width(), self.rowHeight(0))
        inactivePalette = self.palette()
        inactivePalette.setColor(QPalette.HighlightedText, inactivePalette.color(QPalette.Text))
        activePalette = QPalette(inactivePalette)
        activeColor = changedDataSample.palette().color(QPalette.WindowText)
        activePalette.setColor(QPalette.Text, activeColor)
        activePalette.setColor(QPalette.HighlightedText, activeColor)
        self.setItemDelegate(DevicesTableDelegate(inactivePalette, activePalette, self))
        self.resizeRowsToContents()
        self.resizeColumnsToContents()
        self.horizontalHeader().setHighlightSections(False)

    def sizeHintForColumn(self, nColumn):
        return self.columnWidths[nColumn] # ToDo: move it column.configure

    def selectionChanged(self, selected, deselected):
        QTableView.selectionChanged(self, selected, deselected)
        for row in (self.model().mapToSource(index).row() for index in deselected.indexes() if index.column() == 0):
            self.devicesGraphicsView.deactivate(row)
        for row in (self.model().mapToSource(index).row() for index in selected.indexes() if index.column() == 0):
            self.devicesGraphicsView.activate(row)

    def selectDevice(self, selection, active = True):
        self.selectionModel().select(self.model().mapSelectionFromSource(selection), QItemSelectionModel.Select if active else QItemSelectionModel.Deselect)

class DeviceVisual(QLabel):
    def __init__(self, device, viewSelection, activeSample, inactiveSample, graphicsView):
        QLabel.__init__(self, inactiveSample.text()[0] + str(device.number), graphicsView)
        self.device = device
        self.viewSelection = viewSelection
        self.callback = graphicsView.mouseClicked
        self.activeStyleSheet = activeSample.styleSheet()
        self.inactiveStyleSheet = inactiveSample.styleSheet()
        self.deactivate()

    def activate(self, active = True):
        self.device.setWatched(active)
        self.setStyleSheet(self.activeStyleSheet if active else self.inactiveStyleSheet)

    def deactivate(self, inactive = True):
        self.activate(not inactive)

    def isActive(self):
        return self.device.watched

    def toggle(self):
        self.activate(not self.device.watched)

    def mousePressEvent(self, event):
        self.callback(self, event.modifiers())

class DevicesGraphicsView(QGraphicsView):
    def configure(self, devices, deviceDistance, getSelection, selectDevice, activeDeviceVisualSample, inactiveDeviceVisualSample):
        self.deviceDistance = deviceDistance
        self.selectDevice = selectDevice
        offsetSize = self.fontMetrics().boundingRect(inactiveDeviceVisualSample.text()[0])
        self.offset = tuple(float(x) / 2 for x in (offsetSize.width() * FONT_METRICS_CORRECTION, offsetSize.height()))
        self.deviceVisuals = tuple(DeviceVisual(device, getSelection(device.number), activeDeviceVisualSample, inactiveDeviceVisualSample, self) for device in devices)
        self.oldWindowSize = None
        self.recalculate(self.width())
        self.theScene = QGraphicsScene(self)
        self.setScene(self.theScene)
        self.radiationImage = QPixmap('images/radiation.png')

    def afterShow(self): # must be performed after show()
        for deviceVisual in self.deviceVisuals:
            deviceVisual.deactivate()

    def resizeEvent(self, _event = None):
        (width, height) = (self.width(), self.height())
        size = min(width, height)
        if width == height:
            if size != self.oldSize:
                self.recalculate(size)
            return
        # if width > height: # Trying to fit the window to the contents, works bad on Windows
        #     (windowWidth, windowHeight) = (self.mesh.width(), self.mesh.height())
        #     if (windowWidth, windowHeight) != self.oldWindowSize:
        #         self.oldWindowSize = (windowWidth, windowHeight)
        #         self.mesh.resize(windowWidth - (width - size), windowHeight)
        #     return
        self.resize(size, size)

    def recalculate(self, size):
        self.oldSize = size
        self.ppu = float(size) / MAP_TOTAL
        self.field = MAP_FIELD * self.ppu
        self.refresh()

    def refresh(self):
        for deviceVisual in self.deviceVisuals:
            deviceVisual.move(*(int(round(c * self.ppu + self.field - offset)) for (c, offset) in zip((deviceVisual.device.x, deviceVisual.device.y), self.offset)))
        for deviceVisual in self.deviceVisuals:
            for otherDevice in (self.deviceVisuals[device.number] for device in deviceVisual.device.heardDevices):
                self.theScene.addLine(QLineF(deviceVisual.x(), deviceVisual.y(), otherDevice.x(), otherDevice.y()), QColor(0))

    def mouseClicked(self, deviceVisual, modifiers):
        if modifiers == Qt.NoModifier:
            for otherVisual in self.deviceVisuals:
                self.selectDevice(otherVisual.viewSelection, False)
            self.selectDevice(deviceVisual.viewSelection)
        elif modifiers == Qt.ControlModifier:
            self.selectDevice(deviceVisual.viewSelection, not deviceVisual.isActive())
        elif modifiers == Qt.ShiftModifier:
            self.selectDevice(deviceVisual.viewSelection)
            activeVisuals = tuple(v for v in self.deviceVisuals if v.isActive())
            activeVisualsAndRanges = tuple((av, max(self.deviceDistance(av.device, ov.device) for ov in activeVisuals if ov is not av)) for av in activeVisuals)
            for iav in (v for v in self.deviceVisuals if not v.isActive()):
                self.selectDevice(iav.viewSelection, all(self.deviceDistance(iav.device, av.device) <= radius for (av, radius) in activeVisualsAndRanges))

    def activate(self, number, active = True):
        self.deviceVisuals[number].activate(active)

    def deactivate(self, number, inactive = True):
        self.activate(number, not inactive)
