// A source-launch check only: never creates a window, audio output, or settings.
import java.awt.GraphicsEnvironment;

class LauncherDesktopProbe {
    public static void main(String[] args) {
        if (args.length != 0) {
            System.exit(2);
        }
        if (GraphicsEnvironment.isHeadless()) {
            // The shell invokes the existing game CLI to provide its normal error.
            System.exit(3);
        }
    }
}
