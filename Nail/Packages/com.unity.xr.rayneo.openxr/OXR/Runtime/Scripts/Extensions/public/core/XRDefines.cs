namespace com.rayneo.xr.extensions
{
    using System.Runtime.InteropServices;
    public enum XRStateEvent
    {
        //Mag Calibration
        kStateMagNeedCalibrate = 0x6000,
        kStateMagDoingCalibrate = 0x6001,
        kStateMagCalibrateSuccess = 0x6002,
        kStateMagCalibrateFailed = 0x6003,
    }

    public enum XRControlUnit
    {
        kUnitUnknown = 0,
        kUnitHeadTracker,
        kUnitConfiguration,
    }
    public enum FXRControlCommand
    {
        kCtlCmdUnknown = 0,
        kCtlCmdStartMagCalibration,
        kCtlCmdStopMagCalibration,
        kCtlCmdResetRenderParameters,
        kCtlCmdUseATW,
        kCtlCmdUseSinglePass,
    }
    public enum XRImageFormat
    {
        kImageFormatUnknown = 0,
        kImageTextureOES = 0x2001,
        kImageMemoryRGBA = 0x3004,
        kImageMemoryJPEG = 0x3006,
    };
    public enum XRRotateMode
    {
        kDegree0 = 0,
        kDegree90 = 90,
        kDegree180 = 180,
        kDegree270 = 270,
    };

    public class XRCameraFlag
    {
        public static long XR_CAMERA_FLAG_DEFAULT = 0;

        ///仅适用于format为kImageMemory*
        ///由native直接对图像进行旋转，修正sensor安装位置导致的偏转, 非必要不使用
        public static long XR_CAMERA_FLAG_MEMORY_ROTATION_AUTO_CORRECT = (1 << 1);

        ///相机功耗优先
        ///此flag置位后，会尽可能降低相机功耗(降低帧率等措施）
        ///可能会导致输出帧率偏低, 出图时间加长
        public static long XR_CAMERA_FLAG_PREFER_CAMERA_LOW_POWER = (1 << 2);

        ///默认状态下，当前仅当AE收敛才会出图
        ///此flag规避AE收敛中丢帧当过程，收到首帧即出图
        public static long XR_CAMERA_FLAG_DO_NOT_FILTER_BY_AE_STATE = (1 << 3);
    }

    public enum XRCameraProperty
    {
        ///软件层面裁剪图像
        ///仅适用于format为kImageMemory*
        XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION = 0xF001,
    }



    public enum XRPlaneProperty { PLANE_HORIZONTAL_UP, PLANE_HORIZONTAL_DOWN , PLANE_VERTICAL, PLANE_NON };

    [StructLayout(LayoutKind.Sequential)]
    public struct XRRotation
    {
        public float x;
        public float y;
        public float z;
        public float w;

        public XRRotation(float[] r)
        {
            this.x = r[0];
            this.y = r[1];
            this.z = r[2];
            this.w = r[3];

        }
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XRPosition
    {
        public float x;
        public float y;
        public float z;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XRRange
    {
        public float x;
        public float z;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XRPoseInfo
    {
        public ulong timestamp;
        public XRRotation rotation;
        public XRPosition position;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XRPlaneInfo
    {
        public XRPlaneProperty property;
        public XRPoseInfo pose;
        public XRRange local_range;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 100)]
        public float[] local_polygon;
        public int local_polygon_size;
    }

    public enum FXREye
    {
        kEyeLeft = 0,
        kEyeRight = 1,
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XRQuaternionf
    {
        public float x;
        public float y;
        public float z;
        public float w;
    };

    [StructLayout(LayoutKind.Sequential)]
    public struct XRTranslationf
    {
        public float x;
        public float y;
        public float z;
    };

    [StructLayout(LayoutKind.Sequential)]
    public struct XRPosef
    {
        public XRQuaternionf rotation;
        public XRTranslationf position;
    };

    [StructLayout(LayoutKind.Sequential)]
    public struct XRRect
    {
        public int x;
        public int y;
        public int width;   
        public int height;  
    }
}