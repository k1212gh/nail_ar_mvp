
using UnityEngine;
namespace RayNeo.API
{
    /// <summary>
    /// RayNeoInfo 扩展类
    /// </summary>
    public static class RayNeoInfoExtension
    {
        #region Data

        /// <summary>
        /// TAG
        /// </summary>
        private const string TAG = "[RayNeoInfoExtension] ";

        /// <summary>
        /// 设备名称
        /// </summary>
        private static string m_DeviceName;

        /// <summary>
        /// AndroidJavaObject DeviceUtil
        /// </summary>
        private static AndroidJavaObject m_DeviceUtil;
        private static AndroidJavaObject DeviceUtil
        {
            get
            {
                if (m_DeviceUtil == null)
                {
                    m_DeviceUtil = new AndroidJavaClass(PlatformAndroid.SupportPackagePath + ".deviceinfo.DeviceUtil");
                }
                return m_DeviceUtil;
            }
        }

        #endregion

        #region public function


        /// <summary>
        /// 获取设备名
        /// </summary>
        /// <returns></returns>
        public static string GetDeviceName()
        {
            if (m_DeviceName == null) { m_DeviceName = DeviceUtil.CallStatic<string>("getDeviceName"); }
            Debug.Log(TAG + "GetDeviceName(): deviceName = " + m_DeviceName);
            return m_DeviceName;
        }

        #endregion
    }
}
