التوابع
--------

**ماك**

```
xcode-select --install
./get_sdk_mac.sh
```

**دبيان / يوبونتو**

```
./get_sdk.sh
```


برمجة
----

**الباندا**

```
scons -u       # Compile
./flash_h7.sh  # for red panda
./flash.sh     # for other pandas
```

استكشاف الأخطاء وإصلاحها
----

If your panda will not flash and is quickly blinking a single Green LED, use:
```
./recover_h7.sh  # for red panda
./recover.sh     # for other pandas
```

موصل [الباندا](https://comma.ai/shop/products/panda-paw) يمكن استخدامها لوضع الباندا في وضع DFU.


[استخدم](http://github.com/dsigma/dfu-util.git) إذا كان يومض.
