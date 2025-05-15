import numpy as np
import matplotlib.pyplot as plt
from nplab.instrument.stage.SMC100 import SMC100
from qtwidgets import toggle
stage = SMC100(port='COM4', smcID=(1,2), unit='m')
stage.reset_and_configure()
stage.set_state(axis=(1,2), state=True)
stage.show_gui()