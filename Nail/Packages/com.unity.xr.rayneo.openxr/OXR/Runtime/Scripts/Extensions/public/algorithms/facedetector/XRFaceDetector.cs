namespace com.rayneo.xr.extensions
{
    using AOT;
    using System;
    using System.Collections;
    using System.Collections.Generic;
    using System.Runtime.InteropServices;
    using UnityEngine;
    using UnityEngine.UIElements;

    public static class XRFaceDetector
    {
        public static void CreateFaceDetector()
        {
            RayNeoApi_CreateFaceDetector();
        }

        public static void DestroyFaceDetector()
        {
            RayNeoApi_DestroyFaceDetector();
        }

        public static XRTranslationf GetFacePosition()
        {
            return RayNeoApi_GetFaceInCamera();
        }

        public static int CheckFaceState()
        {
            return RayNeoApi_CheckFaceState();
        }


        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_CreateFaceDetector();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern void RayNeoApi_DestroyFaceDetector();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern int RayNeoApi_CheckFaceState();

        [DllImport(XRConstants.XRInterfaces)]
        private static extern XRTranslationf RayNeoApi_GetFaceInCamera();


    }
}