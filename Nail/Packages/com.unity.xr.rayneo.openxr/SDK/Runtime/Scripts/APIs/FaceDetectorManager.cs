using com.rayneo.xr.extensions;
using UnityEngine;
namespace RayNeo
{

    public class FaceDetectorManager
    {
        private static FaceDetectorManager ins = new FaceDetectorManager();
        public static FaceDetectorManager Ins
        {
            get
            {
                return ins;
            }
        }
#if UNITY_EDITOR
#else

        private long m_faceHandle = -1;
#endif
        Vector3 m_posVec3 = Vector3.zero;

        /// <summary>
        /// 获取脸部位置. 
        /// 调用即代表初始化.需要在适当时机调用StopFaceDectector
        /// </summary>
        /// <param name="suc">代表有没有获取到数据.</param>
        /// <returns>如果是Vector3.zero则是没有获取到.</returns>

        public Vector3 GetFacePosition(out bool suc)
        {
#if UNITY_EDITOR
            //编辑器不执行. 后续可以考虑加入debug
            suc = false;

            return Vector3.zero;
#else
            if (m_faceHandle == -1)
            {
                m_faceHandle = XRFaceDetector.CheckFaceState();
                Debug.Log("[MercuryX2]GetFacialData Demo PHandle:" + m_faceHandle);
                XRFaceDetector.CreateFaceDetector();
            }
            if (XRFaceDetector.CheckFaceState() == 1)
            {
                XRTranslationf xrf =  XRFaceDetector.GetFacePosition();
                if (xrf.x == 0 && xrf.y == 0 && xrf.z == 0)
                {
                    suc = false;
                    return Vector3.zero;
                }
                m_posVec3.Set(xrf.x,xrf.y,xrf.z);
            }
            else if(XRFaceDetector.CheckFaceState() == 0)
            {
                suc = false;
                return Vector3.zero;
            }
            suc = true;
            return m_posVec3;
#endif


        }
        public void StartFaceDectector()
        {
#if UNITY_EDITOR
            return;
#else
            XRFaceDetector.CreateFaceDetector();
#endif
        }
        public void StopFaceDectector()
        {
#if UNITY_EDITOR
            return;
#else
            XRFaceDetector.DestroyFaceDetector();
            m_faceHandle = -1;
#endif
        }

    }
}
