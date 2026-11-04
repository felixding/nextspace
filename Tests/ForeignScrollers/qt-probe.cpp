/* An ordinary Qt app: it neither links nor calls the adapter. GPL-2.0-or-later. */
#include <QApplication>
#include <QAbstractScrollArea>
#include <QFile>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QPlainTextEdit>
#include <QScrollArea>
#include <QScrollBar>
#include <QSocketNotifier>
#include <QTableWidget>
#include <QTimer>
#include <QTreeWidget>
#include <QProxyStyle>
#include <cstdio>
#include <unistd.h>
class OverlapStyle : public QProxyStyle {
  int pixelMetric(PixelMetric metric,const QStyleOption *option,const QWidget *widget) const override {
    return metric==PM_ScrollView_ScrollBarOverlap?6:QProxyStyle::pixelMetric(metric,option,widget);
  }
};
int main(int argc, char **argv) {
  QApplication app(argc, argv);
  if(qEnvironmentVariable("PROBE_STYLE")=="overlap") app.setStyle(new OverlapStyle);
  QAbstractScrollArea *area;
  if (qEnvironmentVariable("PROBE_KIND") == "table") {
    auto *table = new QTableWidget(100, 12);
    for (int row=0; row<100; row++) for (int column=0; column<12; column++)
      table->setItem(row,column,new QTableWidgetItem(QString("%1,%2").arg(row).arg(column)));
    area = table;
  } else if(qEnvironmentVariable("PROBE_KIND")=="tree") {
    auto *tree=new QTreeWidget;tree->setColumnCount(3);tree->setHeaderLabels({"Name","Value","Notes"});
    for(int row=0;row<200;row++) new QTreeWidgetItem(tree,{QString("Row %1").arg(row),"Value","Notes"});
    tree->setColumnWidth(0,300);tree->setColumnWidth(1,200);area=tree;
  } else if (qEnvironmentVariable("PROBE_KIND") == "text") {
    auto *text = new QPlainTextEdit;
    for (int row=0; row<200; row++) text->appendPlainText(QString("Left to right line %1").arg(row));
    area = text;
  } else {
    auto *scroll = new QScrollArea;
    auto *content = new QLabel("Left to right content"); content->resize(900, 1200);
    content->setAlignment(Qt::AlignTop | Qt::AlignLeft); scroll->setWidget(content); area = scroll;
  }
  area->setWindowFlag(Qt::FramelessWindowHint);
  area->setWindowTitle("ForeignScrollerQt"); area->resize(480, 360);
  bool ready=false;
  auto report = [&] {
    auto *bar = area->verticalScrollBar();
    QPoint p = bar->mapTo(area, QPoint(0,0));
    QRect viewport = area->viewport()->geometry();
    QJsonObject object{{"event","state"},{"ready",ready},{"value",bar->value()},{"minimum",bar->minimum()},
      {"maximum",bar->maximum()},{"page",bar->pageStep()},{"step",bar->singleStep()},
      {"bar",QJsonArray{p.x(),p.y(),bar->width(),bar->height()}},
      {"viewport",QJsonArray{viewport.x(),viewport.y(),viewport.width(),viewport.height()}},
      {"direction",int(area->viewport()->layoutDirection())}, {"visible",bar->isVisible()}, {"scale",bar->devicePixelRatioF()},
      {"native",bar->property("nextspace-native-scroller").toBool()}};
    if (auto *table=qobject_cast<QTableWidget *>(area)) {
      object["vertical_header"] = table->verticalHeader()->geometry().x();
      object["horizontal_header"] = table->horizontalHeader()->geometry().x();
    }
    if(auto *tree=qobject_cast<QTreeWidget *>(area)) object["horizontal_header"]=tree->header()->geometry().x();
    auto bytes = QJsonDocument(object).toJson(QJsonDocument::Compact);
    puts(bytes.constData()); fflush(stdout);
  };
  QSocketNotifier input(STDIN_FILENO,QSocketNotifier::Read);
  QObject::connect(&input,&QSocketNotifier::activated,[&] {
    char buffer[1024]; if (!fgets(buffer,sizeof(buffer),stdin)) { app.quit(); return; }
    QString line=QString::fromUtf8(buffer).trimmed(); auto parts=line.split(' ');
    if (parts[0]=="quit") {area->close();app.quit();}
    else if (parts[0]=="resize") area->resize(parts[1].toInt(),parts[2].toInt());
    else if (parts[0]=="value") area->verticalScrollBar()->setValue(parts[1].toInt());
    else if (parts[0]=="hide") area->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    else if (parts[0]=="show") area->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOn);
    else if (parts[0]=="rtl") area->setLayoutDirection(Qt::RightToLeft);
    else if (parts[0]=="capture") { area->grab().save(parts[1]); area->verticalScrollBar()->grab().save(parts[1]+".bar.png"); }
    QTimer::singleShot(80,area,[&] {area->repaint();report();puts("{\"event\":\"done\"}");fflush(stdout);});
  });
  QObject::connect(area->verticalScrollBar(),&QScrollBar::valueChanged,[&](int) { report(); });
  area->show();
  QTimer::singleShot(200,area,[&] { ready=true;area->verticalScrollBar()->setValue(qMin(300,area->verticalScrollBar()->maximum()/2)); report(); });
  int result=app.exec(); delete area; return result;
}
