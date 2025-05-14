# from PyQt4 import QtCore
# from PyQt4 import QtGui
from PyQt5.QtWidgets import QGraphicsScene, QApplication
from PyQt5.QtWidgets import QGraphicsView
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QSlider, QWidget
from PyQt5.QtGui import QImage
from PyQt5 import QtCore

from pyueye import ueye


def get_qt_format(ueye_color_format):
    return {ueye.IS_CM_SENSOR_RAW8: QImage.Format_Mono,
            ueye.IS_CM_MONO8: QImage.Format_Mono,
            ueye.IS_CM_RGB8_PACKED: QImage.Format_RGB888,
            ueye.IS_CM_BGR8_PACKED: QImage.Format_RGB888,
            ueye.IS_CM_RGBA8_PACKED: QImage.Format_RGB32,
            ueye.IS_CM_BGRA8_PACKED: QImage.Format_RGB32
            }[ueye_color_format]


class PyuEyeQtView(QWidget):
    update_signal = QtCore.pyqtSignal(QImage, name="update_signal")

    def __init__(self, parent=None, width=800, height=600):
        # super(self.__class__, self).__init__(parent)  # or
        super().__init__(parent)  # ??
        self.setWindowTitle('pyueye example')

        self.image = None

        self.graphics_view = QGraphicsView(self)
        self.v_layout = QVBoxLayout(self)
        self.h_layout = QHBoxLayout()

        self.scene = QGraphicsScene()
        self.graphics_view.setScene(self.scene)
        self.v_layout.addWidget(self.graphics_view)

        self.scene.drawBackground = self.draw_background
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.update_signal.connect(self.update_image)

        self.processors = []
        self.resize(width, height)

        self.v_layout.addLayout(self.h_layout)
        self.setLayout(self.v_layout)

    def on_update_canny_1_slider(self, value):
        pass  # print(value)

    def on_update_canny_2_slider(self, value):
        pass  # print(value)

    def draw_background(self, painter, rect):
        if self.image:
            image = self.image.scaled(rect.width(), rect.height(), QtCore.Qt.KeepAspectRatio)
            painter.drawImage(rect.x(), rect.y(), image)

    def update_image(self, image):
        self.scene.update()

    # this function is not actually used, in main() it is replaced by process_image()
    # if this function is tried it will give an error; ImageData.as_cv_image() is not defined.
    def user_callback(self, image_data):
        return image_data.as_cv_image()  # What is this? ImageData has function self.as_1d_image() but not this

    def handle(self, image_data):
        # print('PyuEyeQtView.handle() startes jevnt og trutt, fra trÃ¥den FrameThread')
        self.image = self.user_callback(self, image_data)  # note it doesn't call function right above
        # as self.user_callback() is overwritten in main(), i.e. view.user_callback = process_image
        self.update_signal.emit(self.image)

        # unlock the buffer so we can use it again
        image_data.unlock()

    def shutdown(self):
        self.close()

    def add_processor(self, callback):
        self.processors.append(callback)


class PyuEyeQtApp:
    def __init__(self, args=[]):
        self.qt_app = QApplication(args)

    def exec_(self):
        self.qt_app.exec_()  # why underscore??

    # self.qt_app.exec()  # it works without underscore
    # single_trailing_underscore_ is used for avoiding conflict with Python keywords (builtin function)
    # I suppose both functions, exec() and exec_(), are defined (to be equal) in the QGuiApplication Class,
    # exec_() is the preferred one (??) to avoid name to be mixed with keyword, but
    # exec() is kept and used in documentation, perhaps preferred when used from outside (??)

    def exit_connect(self, method):
        self.qt_app.aboutToQuit.connect(method)
