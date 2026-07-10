namespace com.rayneo.xr.extensions
{
    using AOT;
    using System;
    using System.Collections;
    using System.Collections.Generic;
    using System.Runtime.InteropServices;
    using UnityEditor;
    using UnityEngine;
    using UnityEngine.XR.OpenXR;

    public static class XRInterfaces
    {

        public delegate void FXRStateEventCallback(UInt32 state, UInt64 timestamp, uint length, IntPtr data);
        public delegate void FXRCameraImageAvailableCallback(IntPtr frame, int length, int format, Int64 timestamp, int width, int height, int context);
        private static List<FXRStateEventCallback> mStateEventCallbackLists = new List<FXRStateEventCallback>();
        private static float[] m_rotOrientation = new float[4];

        //render & OpenXR Settings
        public static void SetBasicXRConfigs(Dictionary<string, int> settings)
        {
            foreach (var item in settings)
            {
                if (item.Key == "ATW" && item.Value == 1)
                {
                    SendCommand((int)XRControlUnit.kUnitConfiguration, (int)FXRControlCommand.kCtlCmdUseATW);
                }
                else if (item.Key == "renderMode" && item.Value == 1)
                {
                    SendCommand((int)XRControlUnit.kUnitConfiguration, (int)FXRControlCommand.kCtlCmdUseSinglePass);
                }
                else if (item.Key == "depthSubmissionMode")
                {
                    int[] prop = new int[1];
                    prop[0] = item.Value;
                    IntPtr ptr = Marshal.AllocHGlobal(sizeof(int));
                    Marshal.Copy(prop, 0, ptr, sizeof(int));
                    XRInterfaces.SetProp("depthSubmissionMode", ptr, sizeof(int));
                }
                else if (item.Key == "trackerAlgorithm")
                {
                    int[] prop = new int[1];
                    prop[0] = item.Value;
                    IntPtr ptr = Marshal.AllocHGlobal(sizeof(int));
                    Marshal.Copy(prop, 0, ptr, sizeof(int));
                    XRInterfaces.SetProp("trackerAlgorithm", ptr, sizeof(int));
                }
                else
                {
                    Debug.LogError("Unknown command " + item.Key);
                }
            }
        }

        public static void Recenter()
        {
            RayNeoApi_RecenterHeadTracker();
        }

        public static void EnableSlamHeadTracker()
        {
            RayNeoApi_EnableSlamHeadTracker();
        }

        public static void DisableSlamHeadTracker()
        {
            RayNeoApi_DisableSlamHeadTracker();
        }

        //public static XRRotation GetNineAxisOrientation()
        //{
        //    RayNeoApi_NineAxisOrientation(m_rotOrientation);
        //    XRRotation r = new(m_rotOrientation);
        //    XRMathUtils.RightHand2UnityLeftHand(ref r);
        //    return r;
        //}

        public static int GetHeadTrackerStatus()
        {
            return RayNeoApi_GetHeadTrackerStatus();
        }

        [MonoPInvokeCallback(typeof(FXRStateEventCallback))]
        private static void StateEventDispatcher(UInt32 state, UInt64 timestamp, uint length, IntPtr data)
        {
            foreach (FXRStateEventCallback item in mStateEventCallbackLists)
            {
                item(state, timestamp, length, data);
            }
        }

        public static bool RegisterStateEventCallback(FXRStateEventCallback callback)
        {
            if (mStateEventCallbackLists.Contains(callback)) return false;
            mStateEventCallbackLists.Add(callback);
            if (mStateEventCallbackLists.Count == 1)
            {
                RayNeoApi_RegisterStateEventCallback(Marshal.GetFunctionPointerForDelegate<FXRStateEventCallback>(StateEventDispatcher));
            }
            return true;
        }

        public static bool UnregisterStateEventCallback(FXRStateEventCallback callback)
        {
            if (!mStateEventCallbackLists.Contains(callback)) return false;
            mStateEventCallbackLists.Remove(callback);
            if (mStateEventCallbackLists.Count == 0)
            {
                RayNeoApi_UnregisterStateEventCallback(Marshal.GetFunctionPointerForDelegate<FXRStateEventCallback>(StateEventDispatcher));
            }
            return true;
        }

        public static int SendCommand(int unit, int command)
        {
            return RayNeoApi_SendCommand(unit, command);
        }

        public static void EnablePlaneDetection()
        {
            RayNeoApi_EnablePlaneDetection();
        }

        public static void DisablePlaneDetection()
        {
            RayNeoApi_DisablePlaneDetection();
        }

        public static int GetPlaneInfo(XRPlaneInfo[] info, int arraySize)
        {
            int len = RayNeoApi_GetPlaneInfo(info, arraySize);
            for (int i = 0; i < len; i++)
            {
                Debug.Log(info[i].pose.rotation.x + " " + info[i].pose.rotation.y + " " + info[i].pose.rotation.z + " " + info[i].pose.rotation.w + "             " + info[i].pose.position.x + " " + info[i].pose.position.y + " " + info[i].pose.position.z);
                XRMathUtils.RightHand2UnityLeftHand(ref info[i].pose.rotation, ref info[i].pose.position);
                Debug.Log("Af:  " + info[i].pose.rotation.x + " " + info[i].pose.rotation.y + " " + info[i].pose.rotation.z + " " + info[i].pose.rotation.w + "             " + info[i].pose.position.x + " " + info[i].pose.position.y + " " + info[i].pose.position.z);
            }
            return len;
        }

        public static int SetProp(string item, IntPtr value, int len)
        {
            return RayNeoApi_SetProp(item, value, len);
        }

        public static int GetProp(string item, [In, Out] IntPtr value, ref int len)
        {
            return RayNeoApi_GetProp(item, value, ref len);
        }


        public static int DeviceType()
        {
            return 0x1000;
        }

        public static int HostType()
        {
            return -1;
        }

        /*
         *  Symbols import from libFFalconXRInterfaces.so
         */
        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_RecenterHeadTracker();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_EnableSlamHeadTracker();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_DisableSlamHeadTracker();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_NineAxisOrientation(float[] orientation);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern float RayNeoApi_NineAxisAzimuth();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern int RayNeoApi_GetHeadTrackerStatus();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_RegisterStateEventCallback(IntPtr callback);

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_UnregisterStateEventCallback(IntPtr callback);

        [DllImport(XRConstants.XRInterfaces)]
        private static extern int RayNeoApi_SendCommand(int unit, int command);

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_EnablePlaneDetection();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_DisablePlaneDetection();

        [DllImport(XRConstants.XRInterfaces, CallingConvention = CallingConvention.Cdecl)]
        private static extern int RayNeoApi_GetPlaneInfo([In, Out] XRPlaneInfo[] info, int arraySize);

        [DllImport(XRConstants.XRInterfaces, CallingConvention = CallingConvention.Cdecl)]
        private static extern int RayNeoApi_SetProp(string item, IntPtr value, int len);

        [DllImport(XRConstants.XRInterfaces, CallingConvention = CallingConvention.Cdecl)]
        private static extern int RayNeoApi_GetProp(string item, [In, Out] IntPtr value, ref int len);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern IntPtr RayNeoApi_OpenCameraDevice(string id);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_CloseCameraDevice(IntPtr device);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_getSupportedResolutions(string id, [In, Out] int[] resolutions, ref int len);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_getCameraList([In, Out] char[][] list, ref int len);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_getOrientation(string id);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern UInt64 RayNeoApi_StartPreviewChannel(IntPtr device, int width, int height, int format, IntPtr callback, [In, Out] IntPtr[] externalStorage, int storageSize, int context);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern UInt64 RayNeoApi_StartPreviewChannelWithParameters(IntPtr device, int width, int height, int frameRate, int format, int[] keys, int lenOfKeys, long[] values, int[] lenOfValues, long flag, IntPtr callback, [In, Out] IntPtr[] externalStorage, int storageSize, int context);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_StopPreviewChannel(IntPtr device, UInt64 uid);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_TakePicture(IntPtr device, int width, int height, int format, IntPtr callback, [In, Out] IntPtr externalStorage, int context);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_TakePictureWithParameters(IntPtr device, int width, int height, int format, int[] keys, int lenOfKeys, long[] values, int[] lenOfValues, long flag, IntPtr callback, [In, Out] IntPtr externalStorage, int context);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_imageUitlsRotate(IntPtr src, int srcWidth, int srcHeight, int format, [In, Out] IntPtr dst, int degree);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_imageUitlsMirror(IntPtr src, int srcWidth, int srcHeight, int format, [In, Out] IntPtr dst);

        [DllImport(XRConstants.XRInterfaces)]
        public static extern int RayNeoApi_imageUitlsScale(IntPtr src, int srcWidth, int srcHeight, int format, [In, Out] IntPtr dst, int dstWidth, int dstHeight);
        [DllImport(XRConstants.XRInterfaces, CallingConvention = CallingConvention.Cdecl)]
        public static extern int RayNeoApi_GetHeadTrackerPose([In, Out] float[] position, [In, Out] float[] rotation);
    }


}