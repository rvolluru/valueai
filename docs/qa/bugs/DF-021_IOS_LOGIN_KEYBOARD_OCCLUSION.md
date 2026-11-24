# DF-021: Mobile login password hidden by keyboard

Reported November 18, 2026. Application UI defect, High / P1.
Status: fixed locally; iOS simulator password-visibility check passed. Physical-device,
Android and longer-form scroll acceptance remain pending. Not deployed or distributed.

## Reproduction and cause

Open Log In on mobile and focus Password with the software keyboard enabled.
The transparent auth modal contained a full-height ScrollView without keyboard
avoidance, allowing the keyboard to cover the form. Simulator hardware-keyboard
mode can separately hide the on-screen keyboard; that setting is not an app fix.

## Change

Place a modal-local SafeAreaProvider and SafeAreaView around the form and use
KeyboardAvoidingView (iOS padding, Android height). Top-align the scroll content
so long sign-up/reset forms can scroll from their beginning within the reduced
viewport. Retain handled keyboard taps so form actions can receive taps while
an input has focus.

## Verification

- Expo production Hermes bundle export and simulator installation passed.
- iPhone 15 Pro Max, iOS 17.2: focus Password with the software keyboard shown;
  the field and Show control are visible above the keyboard.
- This local simulator uses the existing native simulator binary with a freshly
  exported JavaScript bundle; it is not a new EAS/TestFlight release.
- Configuration tests and diff checks passed. No credentials were entered, no
  sign-in was submitted and no production account data was changed.
- Verify scroll reachability for Sign In, create-account confirmation password,
  reset-password and verification code on small phones, landscape, larger text,
  Android resize mode, and physical iOS devices before closing the defect.
