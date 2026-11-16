import ExpoModulesCore
import EntrupySDK

public class EntrupyAppDelegateSubscriber: ExpoAppDelegateSubscriber {
  public func application(_ application: UIApplication,
                          handleEventsForBackgroundURLSession identifier: String,
                          completionHandler: @escaping () -> Void) {
    EntrupyApp.sharedInstance().interceptApplication(application,
      handleEventsForBackgroundURLSession: identifier, completionHandler: completionHandler)
  }
}
