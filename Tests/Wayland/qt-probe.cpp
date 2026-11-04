/* Independent native toolkit comparison. SPDX-License-Identifier: MIT */
#include <QApplication>
#include <QWidget>
#include <QPainter>
#include <QMouseEvent>
#include <cstdio>

class Probe : public QWidget {
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this);
    painter.fillRect(rect(), QColor(192, 192, 192));
    painter.setPen(Qt::black);
    painter.drawText(20, 40, "Qt native Wayland: text and thin lines");
    painter.fillRect(20, 60, 761, 1, Qt::black);
  }
  void mousePressEvent(QMouseEvent *event) override {
    std::printf("{\"event\":\"click\",\"x\":%.0f,\"y\":%.0f}\n", event->position().x(), event->position().y());
    std::fflush(stdout);
  }
};
int main(int argc, char **argv) {
  QApplication app(argc, argv);
  Probe probe;
  probe.setWindowFlag(Qt::FramelessWindowHint);
  probe.setWindowTitle("QtProbe"); probe.resize(801, 601); probe.show();
  return app.exec();
}
