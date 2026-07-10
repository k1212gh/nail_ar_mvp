using com.rayneo.xr.extensions;
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using static com.rayneo.xr.extensions.XRCamera;

namespace RayNeo.API
{

    public enum XRCameraType { 
        RGB,    // RGB 相机
        VGA,    // VGA 相机
    }

    public struct CameraCorpInfo
    {
        public static CameraCorpInfo Default => new CameraCorpInfo(0, 0, 640, 400);
        public int x;
        public int y;
        public int w;
        public int h;
        public CameraCorpInfo(int px, int py, int pw, int ph)
        {
            x = px;
            y = py;
            w = pw;
            h = ph;
            Align();
        }
        public void Align()
        {
            x = Align(x, 8);
            y = Align(y, 8);
            w = Align(w, 8);
            h = Align(h, 8);
        }
        private static int Align(int value, int aligned)
        {
            return (value + (aligned - 1)) & ~(aligned - 1);
        }
    }
    public static class ShareCamera
    {

        #region Data

        /// <summary>
        /// TAG
        /// </summary>
        const string TAG = "[ShareCamera] ";

        /// <summary>
        /// XRCamera Data 
        /// </summary>
        internal const string RGB_CAMERA_ID = "0";
        internal const string VGA_CAMERA_ID = "1";
        internal static XRCamera m_RGBCamera = new XRCamera(RGB_CAMERA_ID);
        internal static XRCamera m_VGACamera = new XRCamera(VGA_CAMERA_ID);

        /// <summary>
        /// 当前 XRCamera 
        /// </summary>
        internal static XRCameraType CurrentCameraType = XRCameraType.RGB;
        private static XRCamera m_CurrentXRCamera = m_RGBCamera;

        internal static Dictionary<ulong, XRCameraHandler> m_Cameras = new Dictionary<ulong, XRCameraHandler>();

        /// <summary>
        /// RGB 相机支持的分辨率
        /// </summary>
        private static XRResolution[] m_RGBSupportResolutions;
        internal static XRResolution[] RGBSupportResolutions { get { if (m_RGBSupportResolutions == null) { m_RGBSupportResolutions = getSupportResolutions(XRCameraType.RGB); }return m_RGBSupportResolutions; } }

        /// <summary>
        /// VGA 相机支持的分辨率
        /// </summary>
        private static XRResolution[] m_VGASupportResolutions;
        internal static XRResolution[] VGASupportResolutions { get { if (m_VGASupportResolutions == null) { m_VGASupportResolutions = getSupportResolutions(XRCameraType.VGA); } return m_VGASupportResolutions; } }

        /// <summary>
        /// 默认分辨率
        /// </summary>
        private static XRResolution DefaultCameraResolution = new XRResolution(640,400);

        #endregion

        #region Interface


        /// <summary>
        /// 打开相机
        /// </summary>
        /// <param name="cameraTpye">Camera 相机类型</param>
        /// <param name="img">显示的UI</param>
        /// <param name="frameRate">获取图片帧率</param>
        /// <returns></returns>
        public static XRCameraHandler OpenCamera(XRCameraType cameraType, RawImage img = null, int frameRate=30)
        {
            return OpenCamera(cameraType, DefaultCameraResolution, img, frameRate);
        }

        /// <summary>
        /// 打开相机
        /// </summary>
        /// <param name="cameraTpye">Camera 相机类型</param>
        /// <param name="resolution">Camera一些设置（分辨率）例如 XRResolution(640,480);</param>
        /// <param name="img">显示的UI</param>
        /// <param name="frameRate">获取图片帧率</param>
        /// <returns></returns>
        public static XRCameraHandler OpenCamera(XRCameraType cameraType, XRResolution resolution, RawImage img = null, int frameRate = 30)
        {
            if (JudgeIsSupportThisResolution(cameraType, resolution)==false) {
                Debug.Log(TAG + $"OpenCamera(): The current camera type does not support this resolution({resolution.width}*{resolution.height})." );
                return null;
            }

            CurrentCameraType = cameraType;
            switch (CurrentCameraType)
            {
                case XRCameraType.RGB:
                    m_CurrentXRCamera = m_RGBCamera;
                    break;
                case XRCameraType.VGA:
                    m_CurrentXRCamera = m_VGACamera;
                    break;
                default:
                    m_CurrentXRCamera = m_RGBCamera;
                    break;
            }

            CameraCorpInfo corp = new CameraCorpInfo(0,0, resolution.width,resolution.height);

            foreach (var item in m_Cameras)
            {
                if (item.Value.width == corp.w && item.Value.height == corp.h)
                {
                    return item.Value;
                }
            }
            var cInfo = new XRCameraHandler();
            //相机开启状态反馈.0代表成功，其它值代表失败
            int cameraValue = 0;

            if (m_Cameras.Count == 0)
            {
                //需要开启相机.
                cameraValue = m_CurrentXRCamera.open();
            }
            if (cameraValue == 0)
            {
                Debug.Log(TAG+"OpenCamera.Success." + corp.x + ":" + corp.y + ":" + corp.w + ":" + corp.h);
                Dictionary<XRCameraProperty, long[]> ps = new Dictionary<XRCameraProperty, long[]>();

                ps.Add(XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION, new long[] { corp.x, corp.y, corp.w, corp.h });

                var previewId = m_CurrentXRCamera.startPreviewChannelWithParameters(corp.w, corp.h, frameRate, XRImageFormat.kImageMemoryRGBA, ps, XRCameraFlag.XR_CAMERA_FLAG_DEFAULT, cInfo);
                cInfo.channelId = previewId;
                cInfo.width = corp.w;
                cInfo.height = corp.h;
                cInfo.m_Image = img;
                cInfo.type = XRImageFormat.kImageMemoryRGBA;
                cInfo.isOes = false;

                m_Cameras[previewId] = cInfo;
                Updater.StartUpdate(cInfo.UpdateT2d);
                return cInfo;
            }
            else
            {
                Debug.LogError(TAG + "OpenCamera.Failed:" + cameraValue);
                return null;
            }
        }

        /// <summary>
        /// 关闭 Camera 
        /// </summary>
        /// <param name="info">之前打开的 XRCameraHandler </param>
        /// <returns></returns>
        public static bool CloseCamera(XRCameraHandler info)
        {
            m_Cameras.Remove(info.channelId);
            Updater.StopUpdate(info.UpdateT2d);
            m_RGBCamera.stopPreviewChannel(info.channelId);

            if (m_Cameras.Count == 0)
            {
                m_RGBCamera.close();
            }
            return true;
        }

        /// <summary>
        /// 获取对应 Camera 类型支持的 分辨率
        /// </summary>
        /// <param name="cameraTpye">Camera 类型</param>
        /// <returns></returns>
        public static XRResolution[] getSupportResolutions(XRCameraType cameraTpye) {
            string cameraID;
            switch (cameraTpye)
            {
                case XRCameraType.RGB:
                    cameraID = RGB_CAMERA_ID;
                    break;
                case XRCameraType.VGA:
                    cameraID = VGA_CAMERA_ID;
                    break;
                default:
                    cameraID = RGB_CAMERA_ID;
                    break;
            }

            return getSupportResolutions(cameraID);
        }

        /// <summary>
        /// 获取对应 Camera 类型支持的 分辨率
        /// </summary>
        /// <param name="cameraID"></param>
        /// <returns></returns>
        public static XRResolution[] getSupportResolutions(string cameraID) { 
            return XRCameraHelper.getSupportResolutions(cameraID);
        }

        #endregion

        #region Other

        
        /// <summary>
        /// 关闭 Camera 
        /// </summary>
        /// <param name="uid"></param>
        /// <returns></returns>
        public static bool CloseCamera(ulong uid)
        {
            if (m_Cameras.TryGetValue(uid, out var info))
            {
                return CloseCamera(info);
            }
            return false;
        }

        /// <summary>
        /// YUV420SP_RGB
        /// </summary>
        /// <param name="yuvs"></param>
        /// <param name="w"></param>
        /// <param name="h"></param>
        /// <param name="call"></param>
        public static void YUV420SP_RGB(byte[] yuvs, int w, int h, Action<int, int, Color32> call)
        {
            int chromaOffset = w * h;
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    int Y = yuvs[y * w + x];
                    int V = yuvs[chromaOffset + (y / 2) * w + 2 * (x / 2)];
                    int U = yuvs[chromaOffset + (y / 2) * w + 2 * (x / 2) + 1];

                    int C = Y - 16;
                    int D = U - 128;
                    int E = V - 128;

                    int R = (298 * C + 409 * E + 128) >> 8;
                    int G = (298 * C - 100 * D - 208 * E + 128) >> 8;
                    int B = (298 * C + 516 * D + 128) >> 8;

                    R = Math.Min(255, Math.Max(0, R));
                    G = Math.Min(255, Math.Max(0, G));
                    B = Math.Min(255, Math.Max(0, B));
                    call(x, y, new Color32((byte)R, (byte)G, (byte)B, 1));
                    //int offset = y * bmpStride + x * 3;
                    //Marshal.WriteByte(bmpPtr + offset, (byte)B);
                    //Marshal.WriteByte(bmpPtr + offset + 1, (byte)G);
                    //Marshal.WriteByte(bmpPtr + offset + 2, (byte)R);
                }
            }

        }


        /// <summary>
        /// 判断 分辨率是否支持
        /// </summary>
        /// <param name="cameraType"></param>
        /// <param name="resolution"></param>
        /// <returns></returns>
        private static bool JudgeIsSupportThisResolution(XRCameraType cameraType, XRResolution resolution) {
            XRResolution[] resolutions;
            switch (cameraType)
            {
                case XRCameraType.RGB:
                    resolutions = RGBSupportResolutions;
                    break;
                case XRCameraType.VGA:
                    resolutions = VGASupportResolutions;
                    break;
                default:
                    resolutions = RGBSupportResolutions;
                    break;
            }

            foreach (var item in resolutions)
            {
                if (item.width == resolution.width ) 
                {
                    if (item.height == resolution.height) {
                        return true;
                    }
                }
            }

            return false;
        }
        #endregion

    }
}
