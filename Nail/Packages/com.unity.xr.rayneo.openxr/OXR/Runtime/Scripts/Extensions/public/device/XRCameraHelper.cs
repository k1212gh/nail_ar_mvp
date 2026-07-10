using System;
using System.Collections.Generic;
using static com.rayneo.xr.extensions.XRInterfaces;
using System.Runtime.InteropServices;
using AOT;
using UnityEngine;
using Unity.Collections.LowLevel.Unsafe;
using Unity.Collections;
using static com.rayneo.xr.extensions.XRCamera;
using UnityEditor;
using System.Linq;


namespace com.rayneo.xr.extensions
{
    public class XRCameraHelper
    {
        static public string[] getCameraList()
        {
            char[][] list = new char[XRConstants.XR_CAMERA_LIST_MAX_LEN][];
            for(int idx = 0; idx < list.Length; idx++)
            {
                list[idx] = new char[XRConstants.XR_CAMERA_NAME_MAX_LEN];
            }

            int len = 0;
            RayNeoApi_getCameraList(list, ref len);

            string[] result = new string[len];
            for (int i = 0; i < len; i++)
            {
                result[i] = new string(list[i]);
            }
            return result;
        }

        static public XRResolution[] getSupportResolutions(string cameraID)
        {
            int[] list = new int[1024 * 2];
            int len = 0;
            RayNeoApi_getSupportedResolutions(cameraID, list, ref len);

            if (len > 0)
            {
                XRResolution[] resolutions = new XRResolution[len / 2];
                for (int idx = 0; idx < len / 2; idx++)
                {
                    resolutions[idx] = new XRResolution(list[idx * 2], list[idx * 2 + 1]);
                }
                return resolutions;
            }
            return null;
        }

        static public int getOrientation(string cameraID)
        {
            return RayNeoApi_getOrientation(cameraID); 
        }
    }

}