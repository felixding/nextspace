/* Embed the existing NSScroller in Qt scrollbar widgets. GPL-2.0-or-later. */
#include "NativeScroller.h"
#include "QtControls.h"
#include "QtEditing.h"
#include "KdeOverrides.h"
#include <QAbstractScrollArea>
#include <QAbstractEventDispatcher>
#include <QApplication>
#include <QEventLoop>
#include <QGenericPlugin>
#include <QHeaderView>
#include <QAbstractButton>
#include <QImage>
#include <QMouseEvent>
#include <QPainter>
#include <QPointer>
#include <QProxyStyle>
#include <QScrollBar>
#include <QStyleFactory>
#include <QStyleOptionSlider>
#include <QTimer>
#include <QTableView>
#include <QTreeView>
#include <cmath>

static unsigned modifiers(Qt::KeyboardModifiers flags)
{
  return (flags.testFlag(Qt::AltModifier) ? NXS_ALT : 0) |
    (flags.testFlag(Qt::ShiftModifier) ? NXS_SHIFT : 0) |
    (flags.testFlag(Qt::ControlModifier) ? NXS_CONTROL : 0) |
    (flags.testFlag(Qt::MetaModifier) ? NXS_SUPER : 0);
}

class NativeBar : public QObject {
public:
  QPointer<QScrollBar> bar;
  NXSScroller *native = nullptr;
  bool detached = false;
  bool pending=false, moved=false, released=false;
  QPointF down,last;
  unsigned downModifiers=0,lastModifiers=0;
  explicit NativeBar(QScrollBar *widget, QObject *owner) : QObject(owner), bar(widget) {
    native = nxs_scroller_create(widget->orientation() == Qt::Horizontal,
      [](void *context, double value) {
        auto *self = static_cast<NativeBar *>(context);
        if (self->bar) {
          int part=nxs_scroller_hit_part(self->native);
          auto action=part==4 ? QAbstractSlider::SliderSingleStepSub : part==5 ? QAbstractSlider::SliderSingleStepAdd :
            part==1 ? QAbstractSlider::SliderPageStepSub : part==3 ? QAbstractSlider::SliderPageStepAdd : QAbstractSlider::SliderNoAction;
          if(action!=QAbstractSlider::SliderNoAction) self->bar->triggerAction(action);
          else self->bar->setSliderPosition(qRound(value));
          self->bar->repaint();
        }
      }, [](void *context) {
        auto *self=static_cast<NativeBar *>(context);
        if(self->moved) {self->moved=false;nxs_scroller_send(self->native,NXS_MOVE,self->last.x(),self->last.y(),self->lastModifiers);}
        if(self->released) {self->released=false;nxs_scroller_send(self->native,NXS_RELEASE,self->last.x(),self->last.y(),self->lastModifiers);}
        QCoreApplication::processEvents(QEventLoop::AllEvents, 1);
      }, this);
    widget->installEventFilter(this);
    connect(widget, &QObject::destroyed, this, [this] {
      bar = nullptr;
      if (nxs_scroller_tracking(native)) {
        detached = true; nxs_scroller_send(native, NXS_RELEASE, 0, 0, 0);
      } else deleteLater();
    });
  }
  ~NativeBar() override { nxs_scroller_destroy(native); }
  void sync() {
    if (bar) nxs_scroller_sync(native, bar->orientation() == Qt::Horizontal ? bar->width() : bar->height(),
      bar->minimum(), double(bar->maximum()) + bar->pageStep(), bar->pageStep(),
      bar->singleStep(), bar->pageStep(), bar->value(), bar->isEnabled());
  }
  bool eventFilter(QObject *object, QEvent *event) override {
    if (!native || !bar) return false;
    if ((event->type()==QEvent::Hide || event->type()==QEvent::UngrabMouse) && nxs_scroller_tracking(native))
      nxs_scroller_send(native,NXS_RELEASE,0,0,0);
    if (event->type() == QEvent::MouseMove || event->type() == QEvent::MouseButtonRelease) {
      if (!pending && !nxs_scroller_tracking(native)) return false;
      auto *mouse = static_cast<QMouseEvent *>(event);
      if(pending) {
        last=mouse->position();lastModifiers=modifiers(mouse->modifiers());
        if(event->type()==QEvent::MouseButtonRelease) released=true;else moved=true;
      } else nxs_scroller_send(native, event->type() == QEvent::MouseButtonRelease ? NXS_RELEASE : NXS_MOVE,
        mouse->position().x(), mouse->position().y(), modifiers(mouse->modifiers()));
      return true;
    }
    if (event->type() == QEvent::MouseButtonPress || event->type()==QEvent::MouseButtonDblClick) {
      auto *mouse = static_cast<QMouseEvent *>(event);
      if (mouse->button() != Qt::LeftButton) return false;
      if(pending || nxs_scroller_tracking(native)) return true;
      down=mouse->position();downModifiers=modifiers(mouse->modifiers());pending=true;moved=released=false;
      // Finish Qt's mouse dispatch before pumping a nested native tracking loop.
      QTimer::singleShot(0,this,[this] {
        pending=false;if(!bar || !bar->isVisible()) return;sync();
        NXSRect slot=nxs_scroller_part(native,6);
        if(QRectF(slot.x,slot.y,slot.width,slot.height).contains(down)) bar->setSliderDown(true);
        nxs_scroller_track(native,down.x(),down.y(),downModifiers);
        if(bar) {bar->setSliderDown(false);bar->update();}
        if(detached) deleteLater();
      });
      return true;
    }
    return QObject::eventFilter(object, event);
  }
};

/* Only scrollbar metrics and painting change. Other widgets retain the app's
 * style. All rectangles and pixels below come from NSScroller itself. */
class NativeStyle : public QProxyStyle {
  NativeBar *control;
public:
  explicit NativeStyle(NativeBar *value) : QProxyStyle(QStyleFactory::create("Fusion")), control(value) {}
  int pixelMetric(PixelMetric metric, const QStyleOption *option, const QWidget *widget) const override {
    if (metric == PM_ScrollBarExtent || metric == PM_ScrollBarSliderMin) return qRound(nxs_scroller_width());
    return QProxyStyle::pixelMetric(metric, option, widget);
  }
  QRect subControlRect(ComplexControl which, const QStyleOptionComplex *option,
                       SubControl part, const QWidget *widget) const override {
    if (which == CC_ScrollBar && control->native) {
      control->sync();
      int nativePart = part == SC_ScrollBarSlider ? 2 : part == SC_ScrollBarSubLine ? 4 :
        part == SC_ScrollBarAddLine ? 5 : 6;
      NXSRect rect = nxs_scroller_part(control->native, nativePart);
      return QRect(qRound(rect.x), qRound(rect.y), qRound(rect.width), qRound(rect.height));
    }
    return QProxyStyle::subControlRect(which, option, part, widget);
  }
  void drawComplexControl(ComplexControl which, const QStyleOptionComplex *option,
                          QPainter *painter, const QWidget *widget) const override {
    if (which != CC_ScrollBar || !control->native) {
      QProxyStyle::drawComplexControl(which, option, painter, widget); return;
    }
    control->sync();
    NXSBitmap bitmap = nxs_scroller_draw(control->native, painter->device()->devicePixelRatioF());
    if (bitmap.pixels) {
      QImage image(bitmap.pixels, bitmap.width, bitmap.height, bitmap.stride, QImage::Format_ARGB32_Premultiplied);
      image.setDevicePixelRatio(painter->device()->devicePixelRatioF());
      painter->drawImage(QPoint(0, 0), image);
    }
  }
};

class Adapter : public QObject {
  NativeEditing editing;
  bool pending = false;
  bool arranging=false;
  QList<QPointer<QAbstractScrollArea>> areas;
  QList<QPointer<QAbstractScrollArea>> observed;
  void arrange(QAbstractScrollArea *area) {
    if(arranging) return;
    arranging=true;placeLeft(area);arranging=false;
  }
  void queue(QAbstractScrollArea *area) {
    if(!observed.contains(area)) observed.append(area);
    if (!areas.contains(area)) areas.append(area);
    if (pending) return;
    pending = true;
    QMetaObject::invokeMethod(this, [this] {
      pending = false; auto current = areas; areas.clear();
      for (auto area : current) if (area) arrange(area);
    },Qt::QueuedConnection);
  }
  static void placeLeft(QAbstractScrollArea *area) {
    auto *bar = area->verticalScrollBar();
    QWidget *container = bar->parentWidget();
    if (!container || container == area || bar->property("nextspaceOriginalControl").toBool() ||
        kdeRetainsOriginalControl(bar) || !bar->isVisible() || area->layoutDirection() == Qt::RightToLeft) return;
    if (container->x() >= area->width()/2) {
      int reserved = qMax(0, container->width() - bar->style()->pixelMetric(QStyle::PM_ScrollView_ScrollBarOverlap, nullptr, bar));
      int left = area->contentsRect().left();
      for (QObject *child : area->children()) {
        auto *widget = qobject_cast<QWidget *>(child);
        if (!widget || widget == container || qobject_cast<QHeaderView *>(widget)) continue;
        if (widget == area->cornerWidget()) widget->move(left, widget->y());
        else widget->move(widget->x() + reserved, widget->y());
      }
      container->move(left, container->y());
    }
    /* Item views update headers independently of their base scroll layout.
     * Anchor them to the resulting viewport rather than translating twice. */
    QRect viewport=area->viewport()->geometry();
    if (auto *table=qobject_cast<QTableView *>(area)) {
      auto *horizontal=table->horizontalHeader();auto *vertical=table->verticalHeader();
      horizontal->setGeometry(viewport.x(),horizontal->y(),viewport.width(),horizontal->height());
      vertical->setGeometry(viewport.x()-vertical->width(),viewport.y(),vertical->width(),viewport.height());
      for (QObject *child:area->children()) if(auto *button=qobject_cast<QAbstractButton *>(child))
        button->setGeometry(vertical->x(),horizontal->y(),vertical->width(),horizontal->height());
    } else if (auto *tree=qobject_cast<QTreeView *>(area)) {
      auto *header=tree->header();header->setGeometry(viewport.x(),header->y(),viewport.width(),header->height());
    }
  }
  bool eventFilter(QObject *object, QEvent *event) override {
    auto *widget = qobject_cast<QWidget *>(object);
    if (!widget) return false;
    if (qgetenv("NEXTSPACE_NATIVE_EDITING") != "off" && editing.filter(widget, event))
      return true;
    if (event->type() == QEvent::Polish)
      if (auto *button = qobject_cast<QAbstractButton *>(widget))
        NativeButtonStyle::attach(button);
    if (qgetenv("NEXTSPACE_SCROLLBARS") == "off") return false;
    if(event->type()==QEvent::Paint) {
      for(auto *parent=widget;parent;parent=parent->parentWidget()) {
        if(auto *area=qobject_cast<QAbstractScrollArea *>(parent)) {arrange(area);break;}
      }
    }
    if (event->type() == QEvent::Polish) {
      if (auto *bar = qobject_cast<QScrollBar *>(widget)) {
        if (!bar->property("nextspace-native-scroller").toBool() &&
            !bar->property("nextspaceOriginalControl").toBool() && !kdeRetainsOriginalControl(bar)) {
          bar->setProperty("nextspace-native-scroller", true);
          auto *control = new NativeBar(bar, this);
          if (control->native) { auto *style = new NativeStyle(control); style->setParent(bar); bar->setStyle(style); }
        }
      }
    }
    switch (event->type()) {
      case QEvent::Resize: case QEvent::Move: case QEvent::Show: case QEvent::Hide:
      case QEvent::LayoutRequest: case QEvent::StyleChange: case QEvent::LayoutDirectionChange:
        for (auto *parent = widget; parent; parent = parent->parentWidget()) {
          if (auto *area = qobject_cast<QAbstractScrollArea *>(parent)) { queue(area); break; }
        }
        break;
      default: break;
    }
    return false;
  }
public:
  /* QGuiApplication owns objects returned by generic plugins. Parenting this
   * to the application would give it a second teardown owner. */
  explicit Adapter(QObject *owner) : QObject(nullptr) {
    owner->installEventFilter(this);
    if (auto *app = qobject_cast<QApplication *>(owner))
      connect(app, &QApplication::focusChanged, this, [this](QWidget *, QWidget *current) {
        editing.focusChanged(current);
      });
    connect(QAbstractEventDispatcher::instance(),&QAbstractEventDispatcher::aboutToBlock,this,[this] {
      for(int i=observed.size()-1;i>=0;i--) {
        if(observed[i]) arrange(observed[i]);else observed.removeAt(i);
      }
    });
  }
};

class Plugin : public QGenericPlugin {
  Q_OBJECT
  Q_PLUGIN_METADATA(IID QGenericPluginFactoryInterface_iid FILE "qt.json")
public:
  QObject *create(const QString &name, const QString &) override {
    if (name.compare("nextspace-scrollbars", Qt::CaseInsensitive) || qEnvironmentVariable("NEXTSPACE_SCROLLBARS") == "off") return nullptr;
    return new Adapter(QCoreApplication::instance());
  }
};
#include "QtScrollers.moc"
