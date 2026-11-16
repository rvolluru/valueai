import ExpoModulesCore
import EntrupySDK

public class JouftEntrupyModule: Module, EntrupyLoginDelegate {
  private var loginPromise: Promise?
  public func definition() -> ModuleDefinition {
    Name("JouftEntrupy")
    AsyncFunction("generateAuthorizationRequest") { () -> String? in
      EntrupyApp.sharedInstance().cleanup()
      return EntrupyApp.sharedInstance().generateSDKAuthorizationRequest()
    }.runOnQueue(.main)
    AsyncFunction("login") { (signed: String, promise: Promise) in
      guard self.loginPromise == nil else {
        promise.reject("BUSY", "Authentication already in progress"); return
      }
      self.loginPromise = promise
      EntrupyApp.sharedInstance().loginDelegate = self
      EntrupyApp.sharedInstance().loginUser(withSignedRequest: signed)
    }.runOnQueue(.main)
    AsyncFunction("startCapture") { (metadata: [String: String]) in
      guard let controller = self.appContext?.utilities?.currentViewController() else {
        throw NSError(domain: "Entrupy", code: 1)
      }
      EntrupyApp.sharedInstance().startCapture(forItem: metadata, viewController: controller)
    }.runOnQueue(.main)
    AsyncFunction("cleanup") {
      EntrupyApp.sharedInstance().cleanup()
    }.runOnQueue(.main)
  }
  public func didLoginUserSuccessfully(_ expirationTime: TimeInterval) {
    loginPromise?.resolve(true); loginPromise = nil
  }
  public func didLoginUserFailWithError(_ errorCode: EntrupyErrorCode, description: String, localizedDescription: String) {
    loginPromise?.reject("LOGIN_FAILED", localizedDescription); loginPromise = nil
  }
}
