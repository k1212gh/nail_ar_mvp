using System;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.EventSystems;

namespace RayNeo
{
    public class Updater : MonoBehaviour
    {
        private static Updater m_UpdateInstance;
        private UnityEvent m_UpdateCallBack = new UnityEvent();
        private static Updater Ins
        {
            get
            {
                if (m_UpdateInstance == null)
                {
                    m_UpdateInstance = new GameObject("RayNeoUpdater").AddComponent<Updater>();
                }

                return m_UpdateInstance;
            }
        }
        public static void StartUpdate(UnityAction ua)
        {
            Ins.m_UpdateCallBack.AddListener(ua);
            //updates.GetInvocationList
        }

        public static void StopUpdate(UnityAction ua)
        {
            Ins.m_UpdateCallBack.RemoveListener(ua);
        }

        private void Update()
        {
            Ins.m_UpdateCallBack.Invoke();
        }
    }
}
