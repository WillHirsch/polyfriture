from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtProperty  # type: ignore
from PyQt6.QtQml import QQmlEngine, QQmlListProperty # type: ignore

from polyfriture.channel_grid_settings import CHANNEL_GRID_COLUMNS

__storeInstance = None

def GetStore():
    global __storeInstance
    if __storeInstance is None:
        __storeInstance = Store()
        # The application owns this shared object, not whichever grid's QML
        # engine first resolves the singleton.
        QQmlEngine.setObjectOwnership(__storeInstance, QQmlEngine.ObjectOwnership.CppOwnership)
    return __storeInstance

class Store(QtCore.QObject):
    dock_states_changed = QtCore.pyqtSignal()
    channel_grid_columns_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dock_states = []
        self._channel_grid_columns = CHANNEL_GRID_COLUMNS.default

    @pyqtProperty(int, notify=channel_grid_columns_changed)
    def channel_grid_columns(self):
        return self._channel_grid_columns

    @channel_grid_columns.setter
    def channel_grid_columns(self, columns):
        self.set_channel_grid_columns(columns)

    @QtCore.pyqtSlot(int)
    def set_channel_grid_columns(self, columns):
        columns = CHANNEL_GRID_COLUMNS.coerce(columns)
        if columns != self._channel_grid_columns:
            self._channel_grid_columns = columns
            self.channel_grid_columns_changed.emit(columns)

    @pyqtProperty(QQmlListProperty, notify=dock_states_changed) # type: ignore
    def dock_states(self):
        return QQmlListProperty(QObject, self, self._dock_states)
