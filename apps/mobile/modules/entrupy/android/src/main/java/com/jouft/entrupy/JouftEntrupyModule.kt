package com.jouft.entrupy

import android.app.Application
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.Promise
import com.entrupy.sdk.app.EntrupyApp
import com.entrupy.sdk.listeners.SdkLoginCallback
import com.entrupy.sdk.model.configMetadataOf

class JouftEntrupyModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("JouftEntrupy")
    AsyncFunction("generateAuthorizationRequest") {
      val application = appContext.reactContext!!.applicationContext as Application
      EntrupyApp.init(application)
      EntrupyApp.sharedInstance().cleanup()
      EntrupyApp.sharedInstance().generateSDKAuthorizationRequest()
    }
    AsyncFunction("login") { signed: String, promise: Promise ->
      EntrupyApp.sharedInstance().loginUser(signed, object : SdkLoginCallback {
        override fun onLoginStarted() {}
        override fun onLoginSuccess(expirationTime: Long) { promise.resolve(true) }
        override fun onLoginError(errorCode: Int, description: String, localizedDescription: String) {
          promise.reject("LOGIN_FAILED", localizedDescription, null)
        }
      })
    }
    AsyncFunction("startCapture") { metadata: Map<String, String> ->
      val activity = appContext.currentActivity ?: error("No active screen")
      activity.runOnUiThread {
        EntrupyApp.sharedInstance().startCapture(
          configMetadata = configMetadataOf(*metadata.map { it.key to it.value }.toTypedArray()),
          showResultScreen = true)
      }
    }
    AsyncFunction("cleanup") { EntrupyApp.sharedInstance().cleanup() }
  }
}
