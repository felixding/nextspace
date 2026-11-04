/* Independent native toolkit comparison. SPDX-License-Identifier: MIT */
#include <QApplication>
#include <QWidget>
#include <QPainter>
#include <QMouseEvent>
#include <QKeyEvent>
#include <QClipboard>
#include <cstdio>

class Probe : public QWidget {
  unsigned copies = 0;
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
  void keyPressEvent(QKeyEvent *event) override {
    if (event->modifiers() & Qt::ControlModifier) {
      if (event->key() == Qt::Key_C) {
        QString line = QStringLiteral("QtProbe:%1:日本語\n").arg(++copies);
        QApplication::clipboard()->setText(line.repeated(4096));
        std::printf("{\"event\":\"clipboard-copy\",\"count\":%u}\n", copies);
        std::fflush(stdout);
        return;
      }
      if (event->key() == Qt::Key_V) {
        QByteArray text = QApplication::clipboard()->text().toUtf8().toBase64();
        std::printf("{\"event\":\"clipboard-paste\",\"base64\":\"%s\"}\n", text.constData());
        std::fflush(stdout);
        return;
      }
    }
    QWidget::keyPressEvent(event);
  }
};
int main(int argc, char **argv) {
  QApplication app(argc, argv);
  Probe probe;
  probe.setWindowFlag(Qt::FramelessWindowHint);
  probe.setWindowTitle("QtProbe"); probe.resize(801, 601); probe.show();
  return app.exec();
}
