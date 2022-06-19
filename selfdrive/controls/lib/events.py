import os
from enum import IntEnum
from typing import Dict, Union, Callable, List, Optional

from cereal import log, car
import cereal.messaging as messaging
from common.conversions import Conversions as CV
from common.realtime import DT_CTRL
from selfdrive.locationd.calibrationd import MIN_SPEED_FILTER
from selfdrive.version import get_short_branch

AlertSize = log.ControlsState.AlertSize
AlertStatus = log.ControlsState.AlertStatus
VisualAlert = car.CarControl.HUDControl.VisualAlert
AudibleAlert = car.CarControl.HUDControl.AudibleAlert
EventName = car.CarEvent.EventName


# Alert priorities
class Priority(IntEnum):
  LOWEST = 0
  LOWER = 1
  LOW = 2
  MID = 3
  HIGH = 4
  HIGHEST = 5


# Event types
class ET:
  ENABLE = 'enable'
  PRE_ENABLE = 'preEnable'
  NO_ENTRY = 'noEntry'
  WARNING = 'warning'
  USER_DISABLE = 'userDisable'
  SOFT_DISABLE = 'softDisable'
  IMMEDIATE_DISABLE = 'immediateDisable'
  PERMANENT = 'permanent'


# get event name from enum
EVENT_NAME = {v: k for k, v in EventName.schema.enumerants.items()}


class Events:
  def __init__(self):
    self.events: List[int] = []
    self.static_events: List[int] = []
    self.events_prev = dict.fromkeys(EVENTS.keys(), 0)

  @property
  def names(self) -> List[int]:
    return self.events

  def __len__(self) -> int:
    return len(self.events)

  def add(self, event_name: int, static: bool=False) -> None:
    if static:
      self.static_events.append(event_name)
    self.events.append(event_name)

  def clear(self) -> None:
    self.events_prev = {k: (v + 1 if k in self.events else 0) for k, v in self.events_prev.items()}
    self.events = self.static_events.copy()

  def any(self, event_type: str) -> bool:
    return any(event_type in EVENTS.get(e, {}) for e in self.events)

  def create_alerts(self, event_types: List[str], callback_args=None):
    if callback_args is None:
      callback_args = []

    ret = []
    for e in self.events:
      types = EVENTS[e].keys()
      for et in event_types:
        if et in types:
          alert = EVENTS[e][et]
          if not isinstance(alert, Alert):
            alert = alert(*callback_args)

          if DT_CTRL * (self.events_prev[e] + 1) >= alert.creation_delay:
            alert.alert_type = f"{EVENT_NAME[e]}/{et}"
            alert.event_type = et
            ret.append(alert)
    return ret

  def add_from_msg(self, events):
    for e in events:
      self.events.append(e.name.raw)

  def to_msg(self):
    ret = []
    for event_name in self.events:
      event = car.CarEvent.new_message()
      event.name = event_name
      for event_type in EVENTS.get(event_name, {}):
        setattr(event, event_type, True)
      ret.append(event)
    return ret


class Alert:
  def __init__(self,
               alert_text_1: str,
               alert_text_2: str,
               alert_status: log.ControlsState.AlertStatus,
               alert_size: log.ControlsState.AlertSize,
               priority: Priority,
               visual_alert: car.CarControl.HUDControl.VisualAlert,
               audible_alert: car.CarControl.HUDControl.AudibleAlert,
               duration: float,
               alert_rate: float = 0.,
               creation_delay: float = 0.):

    self.alert_text_1 = alert_text_1
    self.alert_text_2 = alert_text_2
    self.alert_status = alert_status
    self.alert_size = alert_size
    self.priority = priority
    self.visual_alert = visual_alert
    self.audible_alert = audible_alert

    self.duration = int(duration / DT_CTRL)

    self.alert_rate = alert_rate
    self.creation_delay = creation_delay

    self.alert_type = ""
    self.event_type: Optional[str] = None

  def __str__(self) -> str:
    return f"{self.alert_text_1}/{self.alert_text_2} {self.priority} {self.visual_alert} {self.audible_alert}"

  def __gt__(self, alert2) -> bool:
    return self.priority > alert2.priority


class NoEntryAlert(Alert):
  def __init__(self, alert_text_2: str, visual_alert: car.CarControl.HUDControl.VisualAlert=VisualAlert.none):
    super().__init__("القائد الآلي غير متوفر", alert_text_2, AlertStatus.normal,
                     AlertSize.mid, Priority.LOW, visual_alert,
                     AudibleAlert.refuse, 3.)


class SoftDisableAlert(Alert):
  def __init__(self, alert_text_2: str):
    super().__init__("قم بالتحكم على الفور", alert_text_2,
                     AlertStatus.userPrompt, AlertSize.full,
                     Priority.MID, VisualAlert.steerRequired,
                     AudibleAlert.warningSoft, 2.),


# less harsh version of SoftDisable, where the condition is user-triggered
class UserSoftDisableAlert(SoftDisableAlert):
  def __init__(self, alert_text_2: str):
    super().__init__(alert_text_2),
    self.alert_text_1 = "جاري فصل القائد الآلي"


class ImmediateDisableAlert(Alert):
  def __init__(self, alert_text_2: str):
    super().__init__("قم بالتحكم على الفور", alert_text_2,
                     AlertStatus.critical, AlertSize.full,
                     Priority.HIGHEST, VisualAlert.steerRequired,
                     AudibleAlert.warningImmediate, 4.),


class EngagementAlert(Alert):
  def __init__(self, audible_alert: car.CarControl.HUDControl.AudibleAlert):
    super().__init__("", "",
                     AlertStatus.normal, AlertSize.none,
                     Priority.MID, VisualAlert.none,
                     audible_alert, .2),


class NormalPermanentAlert(Alert):
  def __init__(self, alert_text_1: str, alert_text_2: str = "", duration: float = 0.2, priority: Priority = Priority.LOWER, creation_delay: float = 0.):
    super().__init__(alert_text_1, alert_text_2,
                     AlertStatus.normal, AlertSize.mid if len(alert_text_2) else AlertSize.small,
                     priority, VisualAlert.none, AudibleAlert.none, duration, creation_delay=creation_delay),


class StartupAlert(Alert):
  def __init__(self, alert_text_1: str, alert_text_2: str = "ضع يديك دائما على عاجلة القيادة وأبق عينك على الطريق", alert_status=AlertStatus.normal):
    super().__init__(alert_text_1, alert_text_2,
                     alert_status, AlertSize.mid,
                     Priority.LOWER, VisualAlert.none, AudibleAlert.none, 5.),


# ********** helper functions **********
def get_display_speed(speed_ms: float, metric: bool) -> str:
  speed = int(round(speed_ms * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)))
  unit = 'كلم/س' if metric else 'ميل'
  return f"{speed} {unit}"


# ********** alert callback functions **********

AlertCallbackType = Callable[[car.CarParams, messaging.SubMaster, bool, int], Alert]


def soft_disable_alert(alert_text_2: str) -> AlertCallbackType:
  def func(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
    #if soft_disable_time < int(0.5 / DT_CTRL):
    #  return ImmediateDisableAlert(alert_text_2)
    return SoftDisableAlert(alert_text_2)
  return func

def user_soft_disable_alert(alert_text_2: str) -> AlertCallbackType:
  def func(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
    #if soft_disable_time < int(0.5 / DT_CTRL):
    #  return ImmediateDisableAlert(alert_text_2)
    return UserSoftDisableAlert(alert_text_2)
  return func

def startup_master_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  branch = get_short_branch("")
  if "إعادة" in os.environ:
    branch = "replay"

  return StartupAlert("تحذير: هذا الفرع البرمجي لم يجرب بعد", branch, alert_status=AlertStatus.userPrompt)

def below_engage_speed_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  return NoEntryAlert(f"السرعة أقل من {get_display_speed(CP.minEnableSpeed, metric)}")


def below_steer_speed_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  return Alert(
    f"التوجيه غير متوفر أدناه {get_display_speed(CP.minSteerSpeed, metric)}",
    "",
    AlertStatus.userPrompt, AlertSize.small,
    Priority.MID, VisualAlert.steerRequired, AudibleAlert.prompt, 0.4)


def calibration_incomplete_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  return Alert(
    "المعايرة جارية: %d%%" % sm['المعايرة الحية'].calPerc,
    f"قد فوق {get_display_speed(MIN_SPEED_FILTER, metric)}",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .2)


def no_gps_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  gps_integrated = sm['peripheralState'].pandaType in (log.PandaState.PandaType.uno, log.PandaState.PandaType.dos)
  return Alert(
    "استقبال ضعيف لنظام تحديد المواقع العالمي",
    "إذا كانت السماء مرئية, اتصل بالدعم" if gps_integrated else "تحقق من وضع هوائي GPS",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWER, VisualAlert.none, AudibleAlert.none, .2, creation_delay=300.)


def wrong_car_mode_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  text = "تم تعطيل مثبت السرعة"
  if CP.carName == "honda":
    text = "المفتاح كهربائي مغلق"
  return NoEntryAlert(text)


def joystick_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  axes = sm['testJoystick'].axes
  gb, steer = list(axes)[:2] if len(axes) else (0., 0.)
  vals = f"Gas: {round(gb * 100.)}%, Steer: {round(steer * 100.)}%"
  return NormalPermanentAlert("القيادة بيد التحكم", vals)

def auto_lane_change_alert(CP: car.CarParams, sm: messaging.SubMaster, metric: bool, soft_disable_time: int) -> Alert:
  alc_timer = sm['lateralPlan'].autoLaneChangeTimer
  return Alert(
    "يبدأ تغيير المسار التلقائي في (%d)" % alc_timer,
    "راقب المركبات المحيطة",
    AlertStatus.normal, AlertSize.mid,
    Priority.LOWER, VisualAlert.steerRequired, AudibleAlert.none, .1, alert_rate=0.75)



EVENTS: Dict[int, Dict[str, Union[Alert, AlertCallbackType]]] = {
  # ********** events with no alerts **********

  EventName.stockFcw: {},

  # ********** events only containing alerts displayed in all states **********

  EventName.joystickDebug: {
    ET.WARNING: joystick_alert,
    ET.PERMANENT: NormalPermanentAlert("وضع التحكم باليد"),
  },

  EventName.controlsInitializing: {
    ET.NO_ENTRY: NoEntryAlert("تهيئة النظام"),
  },

  EventName.startup: {
    ET.PERMANENT: StartupAlert("كن مستعدًا لتولي القيادة في أي وقت")
  },

  EventName.startupMaster: {
    ET.PERMANENT: startup_master_alert,
  },

  # Car is recognized, but marked as dashcam only
  EventName.startupNoControl: {
    ET.PERMANENT: StartupAlert("وضع الداش كام"),
  },

  # Car is not recognized
  EventName.startupNoCar: {
    ET.PERMANENT: StartupAlert("وضع الداش كام للمركبات الغير مدعومة"),
  },

  EventName.startupNoFw: {
    ET.PERMANENT: StartupAlert("لم يتم التعرف على المركبة",
                               "افحص منفذ الطاقة مع الاو بي دي",
                               alert_status=AlertStatus.userPrompt),
  },

  EventName.dashcamMode: {
    ET.PERMANENT: NormalPermanentAlert("وضع الداش كام",
                                       priority=Priority.LOWEST),
  },

  EventName.invalidLkasSetting: {
    ET.PERMANENT: NormalPermanentAlert("نظام البقاء في المسار الأصلي قيد التفعيل",
                                       "أطفئ نظام البقاء في المسار الأصلي"),
  },

  EventName.cruiseMismatch: {
    #ET.PERMANENT: ImmediateDisableAlert("openpilot failed to cancel cruise"),
  },

  # openpilot doesn't recognize the car. This switches openpilot into a
  # read-only mode. This can be solved by adding your fingerprint.
  # See https://github.com/commaai/openpilot/wiki/Fingerprinting for more information
  EventName.carUnrecognized: {
    ET.PERMANENT: NormalPermanentAlert("وضع الداش كام",
                                       "المركبة غير معروفة",
                                       priority=Priority.LOWEST),
  },

  EventName.stockAeb: {
    ET.PERMANENT: Alert(
      "انتبه أمامك فوووووورد",
      "خطر الاصطدام وشيك",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.none, 2.),
    ET.NO_ENTRY: NoEntryAlert("نظام التحذير من الاصطدام: خطر الاصطدام"),
  },

  EventName.fcw: {
    ET.PERMANENT: Alert(
      "انتبه أمامك فوووووورد",
      "خطر الاصطدام وشيك",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGHEST, VisualAlert.fcw, AudibleAlert.warningSoft, 2.),
  },

  EventName.ldw: {
    ET.PERMANENT: Alert(
      "تم الكشف عن مغادرة حارة",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.ldw, AudibleAlert.prompt, 3.),
  },

  # ********** events only containing alerts that display while engaged **********

  EventName.gasPressed: {
    ET.PRE_ENABLE: Alert(
      "حرر دواسة الغاز للتشغيل",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .1, creation_delay=1.),
  },

  # openpilot tries to learn certain parameters about your car by observing
  # how the car behaves to steering inputs from both human and openpilot driving.
  # This includes:
  # - steer ratio: gear ratio of the steering rack. Steering angle divided by tire angle
  # - tire stiffness: how much grip your tires have
  # - angle offset: most steering angle sensors are offset and measure a non zero angle when driving straight
  # This alert is thrown when any of these values exceed a sanity check. This can be caused by
  # bad alignment or bad sensor data. If this happens consistently consider creating an issue on GitHub
  EventName.vehicleModelInvalid: {
    ET.NO_ENTRY: NoEntryAlert("فشل تحديد معلومات السيارة"),
    ET.SOFT_DISABLE: soft_disable_alert("فشل تحديد معلومات السيارة"),
  },

  EventName.steerTempUnavailableSilent: {
    ET.WARNING: Alert(
      "التوجيه غير متوفر مؤقتًا",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.prompt, 1.),
  },

  EventName.preDriverDistracted: {
    ET.WARNING: Alert(
      "انتبه",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.promptDriverDistracted: {
    ET.WARNING: Alert(
      "انتبه",
      "السائق مشتت",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.promptDistracted, .1),
  },

  EventName.driverDistracted: {
    ET.WARNING: Alert(
      "افصل على الفور",
      "السائق مشتت",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1),
  },

  EventName.preDriverUnresponsive: {
    ET.WARNING: Alert(
      "المس عجلة القيادة: لم يتم التعرف على السائق",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.promptDriverUnresponsive: {
    ET.WARNING: Alert(
      "المس عجلة القيادة",
      "السائق لا يستجيب",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.MID, VisualAlert.steerRequired, AudibleAlert.promptDistracted, .1),
  },

  EventName.driverUnresponsive: {
    ET.WARNING: Alert(
      "افصل على الفور",
      "السائق لا يستجيب",
      AlertStatus.critical, AlertSize.full,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.warningImmediate, .1),
  },

  EventName.manualRestart: {
    ET.WARNING: Alert(
      "قم بالتحكم",
      "استئناف القيادة يدويًا",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.resumeRequired: {
    ET.WARNING: Alert(
      "توقفت",
      "اضغط على استئناف للذهاب",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.belowSteerSpeed: {
    ET.WARNING: below_steer_speed_alert,
  },

  EventName.preLaneChangeLeft: {
    ET.WARNING: Alert(
      "انطلق يسارًا لبدء تغيير المسار بمجرد أن يصبح آمنًا",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.preLaneChangeRight: {
    ET.WARNING: Alert(
      "توجه يمينًا لبدء تغيير المسار بمجرد أن يصبح آمنًا",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1, alert_rate=0.75),
  },

  EventName.laneChangeBlocked: {
    ET.WARNING: Alert(
      "تم اكتشاف السيارة في النقطة العمياء",
      "",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.prompt, .1),
  },

  EventName.laneChange: {
    ET.WARNING: Alert(
      "تغيير المسارات",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.steerSaturated: {
    ET.WARNING: Alert(
      "قم بالتحكم",
      "يتخطى المنعطف حد التوجيه",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.LOW, VisualAlert.steerRequired, AudibleAlert.promptRepeat, 1.),
  },

  # Thrown when the fan is driven at >50% but is not rotating
  EventName.fanMalfunction: {
    ET.PERMANENT: NormalPermanentAlert("عطل في المروحة", "اتصل بالدعم"),
  },

  # Camera is not outputting frames at a constant framerate
  EventName.cameraMalfunction: {
    ET.PERMANENT: NormalPermanentAlert("عطل في الكاميرا", "اتصل بالدعم"),
  },

  # Unused
  EventName.gpsMalfunction: {
    ET.PERMANENT: NormalPermanentAlert("عطل في نظام تحديد المواقع العالمي", "اتصل بالدعم"),
  },

  # When the GPS position and localizer diverge the localizer is reset to the
  # current GPS position. This alert is thrown when the localizer is reset
  # more often than expected.
  EventName.localizerMalfunction: {
    # ET.PERMANENT: NormalPermanentAlert("Sensor Malfunction", "Contact Support"),
  },

  # ********** events that affect controls state transitions **********

  EventName.pcmEnable: {
    ET.ENABLE: EngagementAlert(AudibleAlert.engage),
  },

  EventName.buttonEnable: {
    ET.ENABLE: EngagementAlert(AudibleAlert.engage),
  },

  EventName.pcmDisable: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
  },

  EventName.buttonCancel: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
  },

  EventName.brakeHold: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("تثبيت الفرامل نشط"),
  },

  EventName.parkBrake: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("فرامل الانتظار معشق"),
  },

  EventName.pedalPressed: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("الضغط على الدواسة",
                              visual_alert=VisualAlert.brakePressed),
  },

  EventName.wrongCarMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: wrong_car_mode_alert,
  },

  EventName.wrongCruiseMode: {
    ET.USER_DISABLE: EngagementAlert(AudibleAlert.disengage),
    ET.NO_ENTRY: NoEntryAlert("الرحلات البحرية التكيفية معطل"),
  },

  EventName.steerTempUnavailable: {
    ET.SOFT_DISABLE: soft_disable_alert("التوجيه غير متوفر مؤقتًا"),
    ET.NO_ENTRY: NoEntryAlert("التوجيه غير متوفر مؤقتًا"),
  },

  EventName.outOfSpace: {
    ET.PERMANENT: NormalPermanentAlert("الذاكرة ممتلئة"),
    ET.NO_ENTRY: NoEntryAlert("الذاكرة ممتلئة"),
  },

  EventName.belowEngageSpeed: {
    ET.NO_ENTRY: below_engage_speed_alert,
  },

  EventName.sensorDataInvalid: {
    ET.PERMANENT: Alert(
      "لا توجد بيانات من أجهزة استشعار الجهاز",
      "أعد تشغيل الجهاز",
      AlertStatus.normal, AlertSize.mid,
      Priority.LOWER, VisualAlert.none, AudibleAlert.none, .2, creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("لا توجد بيانات من أجهزة استشعار الجهاز"),
  },

  EventName.noGps: {
    ET.PERMANENT: no_gps_alert,
  },

  EventName.soundsUnavailable: {
    ET.PERMANENT: NormalPermanentAlert("مكبر الصوت غير موجود", "إعادة تشغيل الجهاز"),
    ET.NO_ENTRY: NoEntryAlert("مكبر الصوت غير موجود"),
  },

  EventName.tooDistracted: {
    ET.NO_ENTRY: NoEntryAlert("مستوى الإلهاء مرتفع جدًا"),
  },

  EventName.overheat: {
    ET.PERMANENT: NormalPermanentAlert("النظام ساخن"),
    ET.SOFT_DISABLE: soft_disable_alert("النظام ساخن"),
    ET.NO_ENTRY: NoEntryAlert("النظام ساخن"),
  },

  EventName.wrongGear: {
    ET.SOFT_DISABLE: user_soft_disable_alert("القير ليس على وضع القيادة"),
    ET.NO_ENTRY: NoEntryAlert("القير ليس على وضع القيادة"),
  },

  # This alert is thrown when the calibration angles are outside of the acceptable range.
  # For example if the device is pointed too much to the left or the right.
  # Usually this can only be solved by removing the mount from the windshield completely,
  # and attaching while making sure the device is pointed straight forward and is level.
  # See https://comma.ai/setup for more information
  EventName.calibrationInvalid: {
    ET.PERMANENT: NormalPermanentAlert("المعايرة غير صحيحة", "أعد تركيب الجهاز وأعد المعايرة"),
    ET.SOFT_DISABLE: soft_disable_alert("المعايرة غير صحيحة: أعد تثبيت الجهاز وإعادة المعايرة"),
    ET.NO_ENTRY: NoEntryAlert("المعايرة غير صحيحة: أعد تثبيت الجهاز وإعادة المعايرة"),
  },

  EventName.calibrationIncomplete: {
    ET.PERMANENT: calibration_incomplete_alert,
    ET.SOFT_DISABLE: soft_disable_alert("المعايرة جارية"),
    ET.NO_ENTRY: NoEntryAlert("المعايرة جارية"),
  },

  EventName.doorOpen: {
    ET.SOFT_DISABLE: user_soft_disable_alert("الباب مفتوح"),
    ET.NO_ENTRY: NoEntryAlert("الباب مفتوح"),
  },

  EventName.seatbeltNotLatched: {
    ET.SOFT_DISABLE: user_soft_disable_alert("حزام الأمان غير مربوط"),
    ET.NO_ENTRY: NoEntryAlert("حزام الأمان غير مربوط"),
  },

  EventName.espDisabled: {
    ET.SOFT_DISABLE: soft_disable_alert("إيقاف ESP"),
    ET.NO_ENTRY: NoEntryAlert("إيقاف ESP"),
  },

  EventName.lowBattery: {
    ET.SOFT_DISABLE: soft_disable_alert("البطارية ضعيفة"),
    ET.NO_ENTRY: NoEntryAlert("البطارية ضعيفة"),
  },

  # Different openpilot services communicate between each other at a certain
  # interval. If communication does not follow the regular schedule this alert
  # is thrown. This can mean a service crashed, did not broadcast a message for
  # ten times the regular interval, or the average interval is more than 10% too high.
  EventName.commIssue: {
    ET.SOFT_DISABLE: soft_disable_alert("مشكلة الاتصال بين العمليات"),
    ET.NO_ENTRY: NoEntryAlert("مشكلة الاتصال بين العمليات"),
  },

  # Thrown when manager detects a service exited unexpectedly while driving
  EventName.processNotRunning: {
    ET.NO_ENTRY: NoEntryAlert("خلل في النظام: إعادة تشغيل الجهاز"),
  },

  EventName.radarFault: {
    ET.SOFT_DISABLE: soft_disable_alert("خطأ الرادار: أعد تشغيل السيارة"),
    ET.NO_ENTRY: NoEntryAlert("خطأ الرادار: أعد تشغيل السيارة"),
  },

  # Every frame from the camera should be processed by the model. If modeld
  # is not processing frames fast enough they have to be dropped. This alert is
  # thrown when over 20% of frames are dropped.
  EventName.modeldLagging: {
    ET.SOFT_DISABLE: soft_disable_alert("نموذج القيادة متخلف"),
    ET.NO_ENTRY: NoEntryAlert("نموذج القيادة متخلف"),
  },

  # Besides predicting the path, lane lines and lead car data the model also
  # predicts the current velocity and rotation speed of the car. If the model is
  # very uncertain about the current velocity while the car is moving, this
  # usually means the model has trouble understanding the scene. This is used
  # as a heuristic to warn the driver.
  EventName.posenetInvalid: {
    ET.SOFT_DISABLE: soft_disable_alert("مخرجات المودل غير مؤكدة"),
    ET.NO_ENTRY: NoEntryAlert("مخرجات المودل غير مؤكدة"),
  },

  # When the localizer detects an acceleration of more than 40 m/s^2 (~4G) we
  # alert the driver the device might have fallen from the windshield.
  EventName.deviceFalling: {
    ET.SOFT_DISABLE: soft_disable_alert("توقف الجهاز عن التثبيت"),
    ET.NO_ENTRY: NoEntryAlert("توقف الجهاز عن التثبيت"),
  },

  EventName.lowMemory: {
    ET.SOFT_DISABLE: soft_disable_alert("ذاكرة منخفضة: أعد تشغيل الجهاز"),
    ET.PERMANENT: NormalPermanentAlert("ذاكرة منخفضة", "أعد تشغيل الجهاز"),
    ET.NO_ENTRY: NoEntryAlert("الذاكرة منخفضة: أعد تشغيل الجهاز"),
  },

  EventName.highCpuUsage: {
    #ET.SOFT_DISABLE: soft_disable_alert("System Malfunction: Reboot Your Device"),
    #ET.PERMANENT: NormalPermanentAlert("System Malfunction", "Reboot your Device"),
    ET.NO_ENTRY: NoEntryAlert("خلل في النظام: أعد تشغيل الجهاز"),
  },

  EventName.accFaulted: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("فشل في تثبيت السرعة"),
    ET.PERMANENT: NormalPermanentAlert("فشل في تثبيت السرعة", ""),
    ET.NO_ENTRY: NoEntryAlert("فشل في تثبيت السرعة"),
  },

  EventName.controlsMismatch: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("عدم تطابق الضوابط"),
  },

  EventName.roadCameraError: {
    ET.PERMANENT: NormalPermanentAlert("خطأ في الكاميرا",
                                       duration=1.,
                                       creation_delay=30.),
  },

  EventName.driverCameraError: {
    ET.PERMANENT: NormalPermanentAlert("خطأ في الكاميرا",
                                       duration=1.,
                                       creation_delay=30.),
  },

  EventName.wideRoadCameraError: {
    ET.PERMANENT: NormalPermanentAlert("خطأ في الكاميرا",
                                       duration=1.,
                                       creation_delay=30.),
  },

  # Sometimes the USB stack on the device can get into a bad state
  # causing the connection to the panda to be lost
  EventName.usbError: {
    ET.SOFT_DISABLE: soft_disable_alert("خطأ USB: أعد تشغيل الجهاز"),
    ET.PERMANENT: NormalPermanentAlert("خطأ USB: أعد تشغيل الجهاز", ""),
    ET.NO_ENTRY: NoEntryAlert("خطأ USB: أعد تشغيل الجهاز"),
  },

  # This alert can be thrown for the following reasons:
  # - No CAN data received at all
  # - CAN data is received, but some message are not received at the right frequency
  # If you're not writing a new car port, this is usually cause by faulty wiring
  EventName.canError: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("خطاء في الكان: افحص التوصيلات"),
    ET.PERMANENT: Alert(
      "خطاء في الكان: افحص التوصيلات",
      "",
      AlertStatus.normal, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, 1., creation_delay=1.),
    ET.NO_ENTRY: NoEntryAlert("خطاء في الكان: افحص التوصيلات"),
  },

  EventName.steerUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("خطأ LKAS: أعد تشغيل السيارة"),
    ET.PERMANENT: NormalPermanentAlert("خطأ LKAS: أعد تشغيل السيارة للتفعيل"),
    ET.NO_ENTRY: NoEntryAlert("خطأ LKAS: أعد تشغيل السيارة"),
  },

  EventName.brakeUnavailable: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("فشل في تثبيت السرعة: أعد تشغيل السيارة"),
    ET.PERMANENT: NormalPermanentAlert("فشل في تثبيت السرعة: أعد تشغيل السيارة للتفعيل"),
    ET.NO_ENTRY: NoEntryAlert("فشل في تثبيت السرعة: أعد تشغيل السيارة"),
  },

  EventName.reverseGear: {
    ET.PERMANENT: Alert(
      "الرجوع للخلف",
      "",
      AlertStatus.normal, AlertSize.full,
      Priority.LOWEST, VisualAlert.none, AudibleAlert.none, .2, creation_delay=0.5),
    ET.SOFT_DISABLE: SoftDisableAlert("الرجوع للخلف"),
    ET.NO_ENTRY: NoEntryAlert("الرجوع للخلف"),
  },

  # On cars that use stock ACC the car can decide to cancel ACC for various reasons.
  # When this happens we can no long control the car so the user needs to be warned immediately.
  EventName.cruiseDisabled: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("مثبت السرعة مطفئ"),
  },

  # For planning the trajectory Model Predictive Control (MPC) is used. This is
  # an optimization algorithm that is not guaranteed to find a feasible solution.
  # If no solution is found or the solution has a very high cost this alert is thrown.
  EventName.plannerError: {
    ET.SOFT_DISABLE: SoftDisableAlert("خطأ في حل المخطط"),
    ET.NO_ENTRY: NoEntryAlert("خطأ في حل المخطط"),
  },

  # When the relay in the harness box opens the CAN bus between the LKAS camera
  # and the rest of the car is separated. When messages from the LKAS camera
  # are received on the car side this usually means the relay hasn't opened correctly
  # and this alert is thrown.
  EventName.relayMalfunction: {
    ET.IMMEDIATE_DISABLE: ImmediateDisableAlert("عطل في الظفيرة"),
    ET.PERMANENT: NormalPermanentAlert("عطل في الظفيرة", "افحص الاجزاء"),
    ET.NO_ENTRY: NoEntryAlert("عطل في الظفيرة"),
  },

  EventName.noTarget: {
    ET.IMMEDIATE_DISABLE: Alert(
      "تم الغاء القائد العربي",
      "لا توجد قيادة قريبة للمركبة",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.disengage, 3.),
    ET.NO_ENTRY: NoEntryAlert("لا توجد قيادة قريبة للمركبة"),
  },

  EventName.speedTooLow: {
    ET.IMMEDIATE_DISABLE: Alert(
      "تم الغاء القائد العربي",
      "السرعة منحفضة جداً",
      AlertStatus.normal, AlertSize.mid,
      Priority.HIGH, VisualAlert.none, AudibleAlert.disengage, 3.),
  },

  # When the car is driving faster than most cars in the training data, the model outputs can be unpredictable.
  EventName.speedTooHigh: {
    ET.WARNING: Alert(
      "السرعة عالية جداً",
      "النظام لا يستطيع القيادة على السرعة العالية",
      AlertStatus.userPrompt, AlertSize.mid,
      Priority.HIGH, VisualAlert.steerRequired, AudibleAlert.promptRepeat, 4.),
    ET.NO_ENTRY: NoEntryAlert("أخفض السرعة للتفعيل"),
  },

  EventName.lowSpeedLockout: {
    ET.PERMANENT: NormalPermanentAlert("فشل في تثبيت السرعة: أعد تشغيل السيارة للتفعيل"),
    ET.NO_ENTRY: NoEntryAlert("فشل في تثبيت السرعة: أعد تشغيل المركبة"),
  },

  EventName.lkasDisabled: {
    ET.PERMANENT: NormalPermanentAlert("نظام البقاء في المسار معطل: شغل نظام البقاء في المسار للتفعيل"),
    ET.NO_ENTRY: NoEntryAlert("نظام البقاء في المسار معطل"),
  },

  EventName.turningIndicatorOn: {
    ET.WARNING: Alert(
      "قم بالتحكم",
      "التوجيه غير متوفر أثناء الدوران",
      AlertStatus.userPrompt, AlertSize.small,
      Priority.LOW, VisualAlert.none, AudibleAlert.none, .2),
  },

  EventName.autoLaneChange: {
    ET.WARNING: auto_lane_change_alert,
  },

  EventName.slowingDownSpeed: {
    ET.PERMANENT: Alert("تباطئ","", AlertStatus.normal, AlertSize.small,
      Priority.MID, VisualAlert.none, AudibleAlert.none, .1),
  },

  EventName.slowingDownSpeedSound: {
    ET.PERMANENT: Alert("تباطئ","", AlertStatus.normal, AlertSize.small,
      Priority.HIGH, VisualAlert.none, AudibleAlert.slowingDownSpeed, 2.),
  },

}
