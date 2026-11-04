/* Test-only observer for an unmodified, distribution-built Qt application.
 * GPL-2.0-or-later. */
#include <QApplication>
#include <QGenericPlugin>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QScrollBar>
#include <QTimer>
#include <cstdio>
class Inspector : public QGenericPlugin {
  Q_OBJECT
  Q_PLUGIN_METADATA(IID QGenericPluginFactoryInterface_iid FILE "inspector.json")
public:
  QObject *create(const QString &,const QString &) override {
    auto *timer=new QTimer;
    connect(timer,&QTimer::timeout,this,[] {
      QJsonArray bars;
      for(QWidget *window:QApplication::topLevelWidgets()) {
        for(QScrollBar *bar:window->findChildren<QScrollBar *>()) {
          if(!bar->isVisible()||bar->orientation()!=Qt::Vertical||bar->maximum()==0) continue;
          QPoint position=bar->mapTo(bar->parentWidget(),QPoint(0,0));
          bars.append(QJsonObject{{"class",bar->metaObject()->className()},{"parent",bar->parentWidget()->metaObject()->className()},
            {"x",position.x()},{"y",position.y()},{"width",bar->width()},{"height",bar->height()},
            {"parent_width",bar->parentWidget()->width()},{"native",bar->property("nextspace-native-scroller").toBool()},
            {"minimum",bar->minimum()},{"maximum",bar->maximum()},{"page",bar->pageStep()},{"value",bar->value()},
            {"scale",bar->devicePixelRatioF()}});
          QString path=qEnvironmentVariable("SCROLLER_INSPECT_CAPTURE");
          if(!path.isEmpty()) {bar->grab().save(path+".bar.png");window->grab().save(path+".png");}
        }
      }
      puts(QJsonDocument(bars).toJson(QJsonDocument::Compact).constData());fflush(stdout);
    });
    timer->start(300);
    return timer;
  }
};
#include "qt-inspector.moc"
