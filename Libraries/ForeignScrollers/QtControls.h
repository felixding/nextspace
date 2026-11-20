/* Standard QWidget drawing backed by the shared GNUstep provider.
 * Qt remains responsible for input, actions and accessibility. GPL-2.0-or-later. */
#include <QAbstractButton>
#include <QCheckBox>
#include <QImage>
#include <QPainter>
#include <QProxyStyle>
#include <QPushButton>
#include <QRadioButton>
#include <QStyleFactory>
#include <QStyleOptionButton>

class NativeButtonStyle final : public QProxyStyle {
  NXSControl *control = nullptr;
  const int kind;

public:
  NativeButtonStyle(QStyle *base, int kind) : QProxyStyle(base), kind(kind) {}
  ~NativeButtonStyle() override { nxs_control_destroy(control); }

  static void attach(QAbstractButton *button)
  {
    if (button->property("nextspaceNativeControl").toBool() ||
        button->property("nextspaceOriginalControl").toBool() ||
        qgetenv("NEXTSPACE_NATIVE_CONTROLS") == "off")
      return;
    int kind;
    auto *type = button->metaObject();
    int requested = button->property("nextspaceControlKind").toInt();
    if (requested == NXS_BUTTON ||
        ((requested == NXS_CHECKBOX || requested == NXS_RADIO) && button->isCheckable()))
      kind = requested;
    else if (type == &QPushButton::staticMetaObject)
      kind = NXS_BUTTON;
    else if (type == &QCheckBox::staticMetaObject)
      kind = NXS_CHECKBOX;
    else if (type == &QRadioButton::staticMetaObject)
      kind = NXS_RADIO;
    else
      return;
    auto *base = QStyleFactory::create(button->style()->name());
    if (!base)
      return;
    auto *style = new NativeButtonStyle(base, kind);
    style->control = nxs_control_create(kind, nullptr, nullptr, nullptr);
    if (!style->control) {
      delete style;
      return;
    }
    button->setProperty("nextspaceNativeControl", true);
    style->setParent(button);
    button->setStyle(style);
  }

  void drawControl(ControlElement element, const QStyleOption *option, QPainter *painter,
                   const QWidget *widget) const override
  {
    const auto *button = qstyleoption_cast<const QStyleOptionButton *>(option);
    const bool supported = (kind == NXS_BUTTON && element == CE_PushButton) ||
        (kind == NXS_CHECKBOX && element == CE_CheckBox) ||
        (kind == NXS_RADIO && element == CE_RadioButton);
    if (supported && button && button->icon.isNull() && button->direction == Qt::LeftToRight &&
        !button->features.testAnyFlags(QStyleOptionButton::Flat | QStyleOptionButton::HasMenu |
            QStyleOptionButton::CommandLinkButton | QStyleOptionButton::DefaultButton) &&
        !button->state.testFlag(State_Sunken) &&
        widget && !widget->property("nextspaceOriginalControl").toBool()) {
      QString title;
      for (qsizetype index = 0; index < button->text.size(); ++index) {
        QChar character = button->text[index];
        if (character != u'&') {
          title.append(character);
        } else if (index + 1 < button->text.size() && button->text[index + 1] == u'&') {
          title.append(character);
          ++index;
        }
      }
      QByteArray text = title.toUtf8();
      NXSControlConfig config{};
      config.size = sizeof(config);
      config.width = button->rect.width();
      config.height = button->rect.height();
      config.enabled = button->state.testFlag(State_Enabled);
      config.state = button->state.testFlag(State_NoChange) ? -1 : button->state.testFlag(State_On);
      config.title = text.constData();
      if (nxs_control_sync(control, &config)) {
        nxs_control_focus(control, button->state.testFlag(State_HasFocus));
        double scale = painter->device()->devicePixelRatioF();
        NXSBitmap bitmap = nxs_control_draw(control, scale);
        if (bitmap.pixels) {
          QImage image(bitmap.pixels, bitmap.width, bitmap.height, bitmap.stride,
                       QImage::Format_ARGB32_Premultiplied);
          image.setDevicePixelRatio(scale);
          painter->drawImage(button->rect.topLeft(), image);
          return;
        }
      }
    }
    QProxyStyle::drawControl(element, option, painter, widget);
  }
};
