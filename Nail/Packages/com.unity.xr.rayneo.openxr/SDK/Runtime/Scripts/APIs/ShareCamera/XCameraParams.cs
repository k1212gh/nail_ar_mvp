using com.rayneo.xr.extensions;
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace RayNeo.API
{
    public class XRCameraHandler : com.rayneo.xr.extensions.XRCamera.ICallback
    {
        //public ShareCameraCallBack callBack;
        public Texture2D texture;
        //public 
        public ulong channelId;
        public int width;
        public int height;
        public XRImageFormat type;
        public bool isOes = false;// is OES

        private bool m_ImgUpdate = false;
        public RawImage m_Image;

        public bool didUpdateThisFrame => m_ImgUpdate;
        public void UpdateT2d()
        {
            if (!m_ImgUpdate)
            {
                return;//not update
            }
            if (texture == null)
            {
                return;
            }
            lock (this)
            {
                if (m_Image != null)
                {
                    m_Image.texture = texture;
                }
                texture.Apply();
                m_ImgUpdate = false;
            }
        }
        public void onImageAvailable(Texture2D image, long timestamp)
        {
            lock (this)
            {
                texture = image;
                m_ImgUpdate = true;

            }
        }

        public void onTextureAvailable(int texID, long timestamp)
        {
            lock (this)
            {

            }
        }

        public void onImageAvailable(IntPtr image, int length, long timestamp)
        {
        }
    }
}
