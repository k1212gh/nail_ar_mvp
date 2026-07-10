using System;
using System.Runtime.InteropServices;
using Unity.Collections.LowLevel.Unsafe;
using UnityEngine;
using UnityEngine.UIElements;

namespace com.rayneo.xr.extensions
{
    /// <summary>
    /// all methods are optimized.
    /// </summary>
    public static class XRImageUtils
    {
        
        static public int rotate(XRImageFormat format, Texture2D src, Texture2D dst, XRRotateMode degree)
        {
            unsafe
            {
                var srcPtr = (IntPtr)src.GetRawTextureData<byte>().GetUnsafePtr();
                var dstPtr = (IntPtr)dst.GetRawTextureData<byte>().GetUnsafePtr();
                return XRInterfaces.RayNeoApi_imageUitlsRotate(srcPtr, src.width, src.height, (int)format, dstPtr, (int)degree);
            }
        }

        static public int mirror(XRImageFormat format, Texture2D src, Texture2D dst)
        {
            unsafe {
                var srcPtr = (IntPtr)src.GetRawTextureData<byte>().GetUnsafePtr();
                var dstPtr = (IntPtr)dst.GetRawTextureData<byte>().GetUnsafePtr();
                return XRInterfaces.RayNeoApi_imageUitlsMirror(srcPtr, src.width, src.height, (int)format, dstPtr);
            }
        }


        static public int scale(XRImageFormat format, Texture2D src, Texture2D dst)
        {
            unsafe
            {
                var srcPtr = (IntPtr)src.GetRawTextureData<byte>().GetUnsafePtr();
                var dstPtr = (IntPtr)dst.GetRawTextureData<byte>().GetUnsafePtr();
                return XRInterfaces.RayNeoApi_imageUitlsScale(srcPtr, src.width, src.height, (int)format, dstPtr, dst.width, dst.height);
            }
        }
            
    }
}