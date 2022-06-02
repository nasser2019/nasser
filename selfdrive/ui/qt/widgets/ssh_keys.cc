#include "selfdrive/ui/qt/widgets/ssh_keys.h"

#include "selfdrive/common/params.h"
#include "selfdrive/ui/qt/api.h"
#include "selfdrive/ui/qt/widgets/input.h"

SshControl::SshControl() : ButtonControl("مفاتيح SSH", "", "تحذير: هذا يمنح SSH الوصول إلى جميع المفاتيح العامة في إعدادات جت هب. لا تدخل أبدًا اسم مستخدم جت هب بخلاف اسم المستخدم الخاص بك. لن يطلب منك موظف الفاصلة أبدًا إضافة اسم مستخدم جت هب الخاص به.") {
  username_label.setAlignment(Qt::AlignRight | Qt::AlignVCenter);
  username_label.setStyleSheet("color: #aaaaaa");
  hlayout->insertWidget(1, &username_label);

  QObject::connect(this, &ButtonControl::clicked, [=]() {
    if (text() == "ADD") {
      QString username = InputDialog::getText("أدخل اسم مستخدم جت هب الخاص بك", this);
      if (username.length() > 0) {
        setText("جار التحميل");
        setEnabled(false);
        getUserKeys(username);
      }
    } else {
      params.remove("GithubUsername");
      params.remove("GithubSshKeys");
      refresh();
    }
  });

  refresh();
}

void SshControl::refresh() {
  QString param = QString::fromStdString(params.get("GithubSshKeys"));
  if (param.length()) {
    username_label.setText(QString::fromStdString(params.get("GithubUsername")));
    setText("إزالة");
  } else {
    username_label.setText("");
    setText("اضف");
  }
  setEnabled(true);
}

void SshControl::getUserKeys(const QString &username) {
  HttpRequest *request = new HttpRequest(this, false);
  QObject::connect(request, &HttpRequest::requestDone, [=](const QString &resp, bool success) {
    if (success) {
      if (!resp.isEmpty()) {
        params.put("GithubUsername", username.toStdString());
        params.put("GithubSshKeys", resp.toStdString());
      } else {
        ConfirmationDialog::alert(QString("Username '%1' has no keys on GitHub").arg(username), this);
      }
    } else {
      if (request->timeout()) {
        ConfirmationDialog::alert("Request timed out", this);
      } else {
        ConfirmationDialog::alert(QString("Username '%1' doesn't exist on GitHub").arg(username), this);
      }
    }

    refresh();
    request->deleteLater();
  });

  request->sendRequest("https://github.com/" + username + ".keys");
}
