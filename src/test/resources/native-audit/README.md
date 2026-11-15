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

`intel-fox-left-edge.png` is the complete, unchanged held-Left frame0008 from
focused Intel native run43720497291, production JAR `88283267`. A delayed capture
let the fox reach the world boundary. Its316 exact rust pixels occupy x0–25;
the old observer excluded x<60 and reported no fox. The independent release
check must still require a moving fox away from a wall, so recognizing this
frame does not turn a wall stop into braking evidence.

SHA-256: `556b6a163aa284021a03e4071c0e26b0185f1baf5a61033d448dc1cf7955f003`.
The image contains only the isolated game window.
