# Android 壳（Capacitor）

把 `server/static` 的两张页面直接装进原生 WebView，拿到安全上下文和摄像头权限。

## 结构

~~~
mobile/
  www/                     web 资源（从 ../server/static 同步）
  capacitor.config.json    appId / webDir / CapacitorHttp
  android/                 Capacitor 生成的原生工程
~~~

## 构建

~~~powershell
$env:ANDROID_HOME="C:\Android"
$env:JAVA_HOME="C:\Program Files\Java\jdk-21.0.11"
cd mobile
Copy-Item ..\server\static\* www\ -Recurse -Force   # 改完页面要重新同步
npx.cmd cap sync android
cd android
.\gradlew.bat assembleDebug
~~~

产物：`mobile/android/app/build/outputs/apk/debug/app-debug.apk`

## 关键配置

| 配置 | 值 | 作用 |
|---|---|---|
| `server.androidScheme` | `https` | WebView 跑在 https://localhost，`isSecureContext` 为真，`getUserMedia` 可用 |
| `server.cleartext` | `true` | 允许访问局域网 http 服务 |
| `plugins.CapacitorHttp` | `enabled` | 请求走原生，绕开 WebView 的混合内容限制 |
| `AndroidManifest` | CAMERA 权限 + usesCleartextTraffic | 摄像头与局域网 |

## 首次使用

1. 手机和电脑连同一个 WiFi
2. 打开 App，点右上角 ⚙ 填电脑地址，例如 `http://192.168.124.9:17800`
3. 点"拍照"进入取景页

## 已知限制

- CapacitorHttp 对 multipart 的支持需要真机验证；若不稳，改用 base64 上传
- WebView 是否支持 `torch` 约束取决于系统 WebView 版本（Android 10+ 一般可用）
- 页面更新后必须 `cap sync android` 再打包，否则装的是旧页面
