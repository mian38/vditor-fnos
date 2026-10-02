# =============================================================================
# R8 / ProGuard 规则
#
# 说明：本App **不使用反射式 JSON 绑定**——所有字段都通过显式的
# `JSONObject.optString("name")` / `optJSONArray("items")` 逐个读取
# （见 data/Models.kt 的 from() 工厂），键名是硬编码字符串，
# 因此**不需要**为反射保类名或字段名。
#
# 真正需要保留的只有两处：
#   1. 注解与签名属性 —— Kotlin 元数据、Material 的 inflate 注解
#   2. Activity —— 系统按类名反射实例化，混淆后会找不到（AGP 默认已保）
# =============================================================================

-keepattributes Signature, *Annotation*, EnclosingMethod, InnerClasses

# Activity / Service / BroadcastReceiver 由系统按类名反射创建，必须原名保留。
# （AGP 自带的默认规则已覆盖，显式再写一遍是为了意图明确、防止后续被误删。）
-keep public class * extends android.app.Activity
-keep public class * extends android.app.Service
-keep public class * extends android.content.BroadcastReceiver

# 协程的 suspend 函数会被编译成带 Continuation 参数的方法，
# 保留参数名以便调试栈可读（不影响功能，仅提升可读性）。
-keepclassmembers class kotlin.coroutines.Continuation {
    kotlinx.coroutines.DebugProbesKt$CoroutineDebugProbesKt$CoroutineScopeKey *;
}

# 关闭 R8 对 org.json 的告警（部分厂商 ROM 存在非标准实现，
# 如高通机型上 JSONObject.optString 签名不同，会触发规则不匹配告警）。
-dontwarn org.json.**
-dontwarn javax.net.ssl.**
