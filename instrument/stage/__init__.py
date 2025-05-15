"""
Base class and interface for Stages.
"""
from __future__ import division
from __future__ import print_function

from builtins import str
from builtins import zip
from builtins import range
#from past.utils import old_div
__author__ = 'alansanders, richardbowman'

import numpy as np
from collections import OrderedDict
import itertools
from nplab.instrument import Instrument
#from nplab.instrument.stage.SMC100 import SMC100
import time
import threading
from nplab.utils.gui import *
from nplab.utils.gui import uic
from nplab.ui.ui_tools import UiTools
import nplab.ui
from nplab.ui.widgets.position_widgets import XYZPositionWidget
from qtwidgets import Toggle
import inspect
from functools import partial
from nplab.utils.formatting import engineering_format
import collections


class Stage(Instrument):
    """A class representing motion-control stages.
    
    This class primarily provides two things: the ability to find the position
    of the stage (using `Stage.position` or `Stage.get_position(axis="a")`), 
    and the ability to move the stage (see `Stage.move()`).
    
    Subclassing Notes
    -----------------
    The minimum you need to do in order to subclass this is to override the
    `move` method and the `get_position` method.  NB you must handle the case
    where `axis` is specified and where it is not.  For `move`, `move_axis` is
    provided, which will help emulate single-axis moves on stages that can't 
    make them natively.
    
    In the future, a class factory method might be available, that will 
    simplify the emulation of various features.
    """
    axis_names = ('x', 'y', 'z')
    def __init__(self,unit = 'm'):#, scale={'m': 1e-3}):
        Instrument.__init__(self)
        self.unit = unit
        #self.stage_unit = list(scale.keys)[0]  # e.g. SMC100 natively uses mm. need to convert m --> mm
        #self.scale = list(scale.values)[0]  # e.g. SMC100 natively uses mm. need to convert m --> mm

    def move(self, pos, axis=None, relative=False):
        raise NotImplementedError("You must override move() in a Stage subclass")

    def move_rel(self, position, axis=None):
        """Make a relative move, see move() with relative=True."""
        self.move(position, axis, relative=True)

    def move_axis(self, pos, axis, relative=False, **kwargs):
        """Move along one axis.
        
        This function moves only in one axis, by calling self.move with 
        appropriately generated values (i.e. it supplies all axes with position
        instructions, but those not moving just get the current position).
        
        It's intended for use in stages that don't support single-axis moves."""
        if axis not in self.axis_names:
            raise ValueError("{0} is not a valid axis, must be one of {1}".format(axis, self.axis_names))

        full_position = np.zeros((len(self.axis_names))) if relative else self.position
        full_position[self.axis_names.index(axis)] = pos
        self.move(full_position, relative=relative, **kwargs)

    def get_position(self, axis=None):
        raise NotImplementedError("You must override get_position in a Stage subclass.")
    
    def set_state(self, axis=None, state=True):
        """Enable/Disable servo control"""
        raise NotImplementedError("You must override set_state() in a Stage subclass")

    def select_axis(self, iterable, axis):
        """Pick an element from a tuple, indexed by axis name."""
        assert axis in self.axis_names, ValueError("{0} is not a valid axis name.".format(axis))
        return iterable[self.axis_names.index(axis)]

    def _get_position_proxy(self):
        """Return self.get_position() (this is a convenience to avoid having
        to redefine the position property every time you subclass - don't call
        it directly)"""
        return self.get_position()
    position = property(fget=_get_position_proxy, doc="Current position of the stage (all axes)")

    def is_moving(self, axes=None):
        """Returns True if any of the specified axes are in motion."""
        raise NotImplementedError("The is_moving method must be subclassed and implemented before it's any use!")

    def wait_until_stopped(self, axes=None):
        """Block until the stage is no longer moving."""
        while self.is_moving(axes=axes):
            time.sleep(0.01)

    def get_qt_ui(self):
        if self.unit == 'base':
            return StageUI(self)
        elif self.unit == 'm':
            return StageUI(self, stage_step_min=1E-7, stage_step_max=1e-2, default_step=1e-7)
        elif self.unit == 'step':
            return StageUI(self, stage_step_min=1, stage_step_max=1000.0, default_step=1.0)
        elif self.unit == 'deg':
            return StageUI(self, stage_step_min=0.1, stage_step_max=360, default_step=1.0)
        else:
            self._logger.warn('Tried displaying a GUI for an unrecognised unit: %s' % self.unit)

    def get_axis_param(self, get_func, axis=None):
        if axis is None:
            return tuple(get_func(axis) for axis in self.axis_names)
        elif isinstance(axis, collections.Sequence) and not isinstance(axis, str):
            return tuple(get_func(ax) for ax in axis)
        else:
            return get_func(axis)

    def set_axis_param(self, set_func, value, axis=None):
        if axis is None:
            if isinstance(value, collections.Sequence):
                tuple(set_func(v, axis) for v,axis in zip(value, self.axis_names))
            else:
                tuple(set_func(value, axis) for axis in self.axis_names)
        elif isinstance(axis, collections.Sequence) and not isinstance(axis, str):
            if isinstance(value, collections.Sequence):
                tuple(set_func(v, ax) for v,ax in zip(value, axis))
            else:
                tuple(set_func(value, ax) for ax in axis)
        else:
            set_func(value, axis)

    # TODO: stored dictionary of 'bookmarked' locations for fast travel






class StageUI(QtWidgets.QWidget, UiTools):
    update_ui = QtCore.Signal([int], [str])

    def __init__(self, stage, parent=None, stage_step_min=1e-9, stage_step_max=1e-3, default_step=1e-6):
        assert isinstance(stage, Stage), "instrument must be a Stage"
        super(StageUI, self).__init__()
        self.stage = stage
        #self.setupUi(self)
        self.step_size_values = step_size_dict(stage_step_min, stage_step_max,unit = self.stage.unit)
        self.step_size = [self.step_size_values[list(self.step_size_values.keys())[0]] for axis in stage.axis_names]
        self.update_ui[int].connect(self.update_positions)
        self.update_ui[str].connect(self.update_positions)
        self.create_axes_layout(default_step)
        self.update_positions()

    def move_axis_absolute(self, position, axis):
        self.stage.move(position, axis=axis, relative=False)
        if type(axis) == str:
            self.update_ui[str].emit(axis)
        elif type(axis) == int:
            self.update_ui[int].emit(axis)

    def move_axis_relative(self, index, axis, dir=1):
        current_position = self.stage.position[index]
        if dir == -1:
            result = current_position - self.step_size[index]
            if result <= 0:
                print("Cannot go negative coordinate")
                self.stage.home(axis=axis)

        self.stage.move(dir * self.step_size[index], axis=axis, relative=True)
          
        if type(axis) == str:
            #    axis = QtCore.QString(axis)
            self.update_ui[str].emit(axis)
        elif type(axis) == int:
            self.update_ui[int].emit(axis)

    def zero_all_axes(self, axis):
        try:
            self.stage.home(axis=axis, waitStop = False)
            time.sleep(0.1)
            self.stage.home(axis=axis, waitStop = True)
        except:
            print("Other actuators will be added")

        #pass
#        for axis in axes:
#            self.move_axis_absolute(0, axis)
    
    def set_stage_state(self, axis, state):
        self.stage.set_state(axis=axis, state=state)

    

    def create_axes_layout(self, default_step=1e-6, arrange_buttons='cross', rows=None):
        
        cartesean = ('X', 'Z', 'extra')

        if rows is None:
            rows = np.ceil(np.sqrt(len(self.stage.axis_names)))
        rows = int(rows)

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'stage.ui'), self)
        
        self.update_pos_button.clicked.connect(partial(self.update_positions, None))
        
        # Add per-axis RST buttons at the top
        top_layout = self.horizontalLayout
        self.rst_buttons = []  # Store buttons if needed later
        
        for i, ax in enumerate(self.stage.axis_names):
            rst_button = QtWidgets.QPushButton(f"RST {cartesean[i]}", self)
            rst_button.clicked.connect(self.homing_stage)
            top_layout.insertWidget(i, rst_button)  # Insert before "Update Positions"
            self.rst_buttons.append(rst_button)
        
        # Rest of your method...
        path = os.path.dirname(os.path.realpath(nplab.ui.__file__))
        icon_size = QtCore.QSize(12, 12)
        self.positions = []
        self.set_positions = []
        self.set_position_buttons = []
        self.set_state_buttons = []


        for i, ax in enumerate(self.stage.axis_names):
            # Top part of the UI: Absolute movement and enable/disable stage
            col = 4 * ((i// rows))

            position = QtWidgets.QLineEdit('', self)
            position.setReadOnly(True)
            self.positions.append(position)

            set_position = QtWidgets.QLineEdit('0', self)
            set_position.setMinimumWidth(40)
            self.set_positions.append(set_position)

            set_position_button = QtWidgets.QPushButton('', self)
            set_position_button.setIcon(QtGui.QIcon(os.path.join(path, 'go.png')))
            set_position_button.setIconSize(icon_size)
            set_position_button.resize(icon_size)
            set_position_button.clicked.connect(self.button_pressed)
            self.set_position_buttons.append(set_position_button)

            set_state_button = Toggle()
            set_state_button.setChecked(True) 
            set_state_button.setIconSize(icon_size)
            set_state_button.resize(icon_size)
            set_state_button.toggled.connect(self.handle_toggled)
            self.set_state_buttons.append(set_state_button)

            # set_rst_button = QtWidgets.QPushButton('', self)
            # #set_rst_button.setMinimumWidth(100)
            # set_rst_button.setIcon(QtGui.QIcon(os.path.join(path, 'zero.png')))
            # set_rst_button.setIconSize(icon_size)
            # set_rst_button.resize(icon_size)
            # set_rst_button.clicked.connect(self.homing_stage)
            # self.set_rst_buttons.append(set_rst_button)
            

            # for each stage axis add a label, a field for the current position,
            # a field to set a new position and a button to set a new position ..

            self.info_layout.addWidget(QtWidgets.QLabel(str(cartesean[i]), self), i % rows, col)
            self.info_layout.addWidget(position, i % rows, col + 1)
            self.info_layout.addWidget(set_position, i % rows, col + 2)
            self.info_layout.addWidget(set_position_button, i % rows, col + 3)
            self.info_layout.addWidget(set_state_button, i % rows, col + 4)
            self.info_layout.setSpacing(20)
            #self.info_layout.addWidget(set_rst_button, i % rows, col + 5)

            # Bottom part of the UI: Relative movements

            if i % rows == 0:
                if arrange_buttons == 'cross':
                    group = QtWidgets.QGroupBox('axes {0}'.format(1 + ((i//rows))), self)
                    layout = QtWidgets.QGridLayout()
                    layout.setSpacing(3)
                    group.setLayout(layout)
                    self.axes_layout.addWidget(group, 0, (i// rows))
                    offset = 0
                elif arrange_buttons == 'stack':
                    layout = self.axes_layout
                    offset = 7 * (i//rows)
                else:
                    raise ValueError('Unrecognised arrangment: %s' % arrange_buttons)

            step_size_select = QtWidgets.QComboBox(self)
            step_size_select.addItems(list(self.step_size_values.keys()))
            step_size_select.activated[str].connect(partial(self.on_activated, i))
            step_str = engineering_format(default_step, self.stage.unit)
            step_index = list(self.step_size_values.keys()).index(step_str)
            step_size_select.setCurrentIndex(step_index)
            layout.addWidget(QtWidgets.QLabel(str(cartesean[i]), self), i % rows, 5 + offset)
            layout.addWidget(step_size_select, i % rows, 6 + offset)
            if i % 3 == 0 and arrange_buttons == 'cross':
                layout.addItem(QtWidgets.QSpacerItem(12, 0), 0, 4)

            plus_button = QtWidgets.QPushButton('', self)
            plus_button.clicked.connect(partial(self.move_axis_relative, i, ax, 1))
            minus_button = QtWidgets.QPushButton('', self)
            minus_button.clicked.connect(partial(self.move_axis_relative, i, ax, -1))
            if arrange_buttons == 'cross':
                if i % rows == 0:
                    plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'right.png')))
                    minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'left.png')))
                    layout.addWidget(minus_button, 1, 0)
                    layout.addWidget(plus_button, 1, 2)
                elif i % rows == 1:
                    plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'down.png')))
                    minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'up.png')))
                    layout.addWidget(plus_button, 2, 1)
                    layout.addWidget(minus_button, 0, 1)
                elif i % rows == 2:
                    plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'down.png')))
                    minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'up.png')))
                    layout.addWidget(plus_button, 0, 3)
                    layout.addWidget(minus_button, 2, 3)
            elif arrange_buttons == 'stack':
                plus_button.setIcon(QtGui.QIcon(os.path.join(path, 'right.png')))
                minus_button.setIcon(QtGui.QIcon(os.path.join(path, 'left.png')))
                layout.addWidget(minus_button, i % rows, 0 + offset)
                layout.addWidget(plus_button, i % rows, 1 + offset)
            else:
                raise ValueError('Unrecognised arrangment: %s' % arrange_buttons)
            plus_button.setIconSize(icon_size)
            plus_button.resize(icon_size)
            minus_button.setIconSize(icon_size)
            minus_button.resize(icon_size)

    def button_pressed(self, *args, **kwargs):
        sender = self.sender()
        if sender in self.set_position_buttons:
            index = self.set_position_buttons.index(sender)
            axis = self.stage.axis_names[index]
            position = float(self.set_positions[index].text())
            self.move_axis_absolute(position, axis)

    def handle_toggled(self, state):
        sender = self.sender()
        #if isinstance(self.stage, SMC100):
        if sender in self.set_state_buttons:
            index = self.set_state_buttons.index(sender)
            axis = self.stage.axis_names[index]
            print(f"state = {state}")
        #try:
        self.set_stage_state(axis, state)
        # except:
        #     print("Other actuators will be added")
        #     print(f"current stage is {self.stage}")
    
    def homing_stage(self):
        sender = self.sender()
        #if isinstance(self.stage, SMC100):
        if sender in self.rst_buttons:
            index = self.rst_buttons.index(sender)
            axis = self.stage.axis_names[index]
        
        self.stage.reset_and_configure_each(axis)


    def on_activated(self, index, value):
        # print self.sender(), index, value
        self.step_size[index] = self.step_size_values[value]

    @QtCore.Slot(int)
    # @QtCore.pyqtSlot('QString')
    @QtCore.Slot(str)
    def update_positions(self, axis=None):
        if axis not in self.stage.axis_names:
            axis = None
        if axis is None:
            for axis in self.stage.axis_names:
                self.update_positions(axis=axis)
        else:
            i = self.stage.axis_names.index(axis)
            try:
                p = engineering_format(self.stage.position[i], base_unit=self.stage.unit, digits_of_precision=4)
            except ValueError:
                p = '0 mm'
            self.positions[i].setText(p)
    
    



def step_size_dict(smallest, largest, mantissas=[1, 2, 5],unit = 'm'):
    """Return a dictionary with nicely-formatted distances as keys and metres as values."""
    log_range = np.arange(np.floor(np.log10(smallest)), np.floor(np.log10(largest)) + 1)
    steps = [m * 10 ** e for e in log_range for m in mantissas if smallest <= m * 10 ** e <= largest]
    return OrderedDict((engineering_format(s, unit), s) for s in steps)



class DummyStage(Stage):
    """A stub stage for testing purposes, prints moves to the console."""

    def __init__(self):
        super(DummyStage, self).__init__()
        #self.axis_names = ('x1', 'y1', 'z1', 'x2', 'y2', 'z2')
        self.axis_names = (1,2,)
        self.max_voltage_levels = [4095 for ch in range(len(self.axis_names))]
        self._position = np.zeros((len(self.axis_names)), dtype=np.float64)
        self.piezo_levels = [50,50,50,50,50,50]

    def move(self, position, axis=None, relative=False):
        def move_axis(position, axis):
            if relative:
                self._position[self.axis_names.index(axis)] += position
            else:
                self._position[self.axis_names.index(axis)] = position
        self.set_axis_param(move_axis, position, axis)
        #i = self.axis_names.index(axis)
        #if relative:
        #    self._position[i] += position
        #else:
        #    self._position[i] = position
            # print "stage now at", self._position

    #def move_rel(self, position, axis=None):
    #    self.move(position, relative=True)

    def get_position(self, axis=None):
        return self.get_axis_param(lambda axis: self._position[self.axis_names.index(axis)], axis)

    position = property(get_position)

    def get_qt_ui(self):
        #return StageUI(self,show_z_pos=False)
        return StageUI(self, stage_step_min=1E-7, stage_step_max=1e-2, default_step=1e-7)



if __name__ == '__main__':
    import sys
    from nplab.utils.gui import get_qt_app

    stage = DummyStage()
    print(stage.move(2e-6, axis=('x1', 'x2')))
    print(stage.get_position())
    print(stage.get_position('x1'))
    print(stage.get_position(['x1', 'y1']))

    app = get_qt_app()
    ui = stage.get_qt_ui()
    ui.show()
    sys.exit(app.exec_())
