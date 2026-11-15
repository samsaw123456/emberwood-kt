# Native screenshot regression

`intel-presentation-marker.png` is an unchanged 32×32 upper-left crop of the
actual Intel Mac capture from CI run 43715704373, production JAR `88283267`.
The original is `build/ci-native-final-macos-intel/build/controls-native-app/external-capture.png`,
SHA-256 `4160d63e21c9454ec7ce110073e7bf4ba86c246161119063508c180a187da6b8`.

The intended RGB (251, 1, 4) test marker became (250, 3, 1) in capture, causing
the old exact-color presentation check to reject every case before input.
The regression applies those observed channel shifts to the replacement pattern;
native reruns separately verify actual rendering and capture. The crop contains
no user desktop or personal data.
