using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using AOT;
using UnityEngine;
using Unity.Collections.LowLevel.Unsafe;
using Unity.Collections;
using System.Collections;
using System.Linq;
using System.Numerics;
using static com.rayneo.xr.extensions.XRInterfaces;

namespace com.rayneo.xr.extensions
{
    public class XRCamera
    {
        public interface ICallback
        {
            //GPU Image
            public abstract void onTextureAvailable(int texID, Int64 timestamp);

            //CPU Image
            public abstract void onImageAvailable(Texture2D image, Int64 timestamp);

            //JPEG Image
            public abstract void onImageAvailable(IntPtr image, int length, Int64 timestamp);

        }

        private class XRChannel
        {
            public ICallback callback;
            public Dictionary<IntPtr, Texture2D> mTextureList = new Dictionary<IntPtr, Texture2D>();
            private int queueSize;
            private int width = 0;
            private int height = 0;
            private XRImageFormat format = XRImageFormat.kImageFormatUnknown;

            public XRChannel(string cameraID, int width, int height, XRImageFormat format, XRRect roi, long flag, ICallback callback, int bufferSize = 3) 
            {
                this.width = width;
                this.height = height;
                this.format = format;
                this.callback = callback;
                this.queueSize = bufferSize;

                if(format == XRImageFormat.kImageMemoryJPEG || format == XRImageFormat.kImageMemoryRGBA)
                {
                    if (format == XRImageFormat.kImageMemoryJPEG)
                    {

                    }
                    else if (format == XRImageFormat.kImageMemoryRGBA)
                    {
                        bool bRotate = ((flag & XRCameraFlag.XR_CAMERA_FLAG_MEMORY_ROTATION_AUTO_CORRECT) != 0);
                        bool bCrop = (roi.width != 0 && roi.height != 0);
                        if (bCrop)
                        {
                            this.width = roi.width;
                            this.height = roi.height;
                        }

                        if (bRotate)
                        {
                            int orientation = XRCameraHelper.getOrientation(cameraID);
                            if(orientation == 90 || orientation == 180)
                            {
                                int tmp = this.width;
                                this.width = this.height;
                                this.height = tmp;
                            }
                        }
         
                        for (int i = 0; i < bufferSize; i++)
                        {
                            unsafe
                            {
                                var texture = new Texture2D(this.width, this.height, TextureFormat.BGRA32, false);
                                texture.name = "XRChannel";
                                var nativeArray = texture.GetRawTextureData<byte>();
                                var ptr = (IntPtr)nativeArray.GetUnsafePtr();
                                mTextureList.Add(ptr, texture);
                            }
                        }
                    }
                }

            }

            public void ReleaseAll()
            {
                foreach (var item in mTextureList)
                {
                    GameObject.Destroy(item.Value);
                }
                mTextureList.Clear();
            }

            private int ALIGN(int value, int aligned)
            {
                return (value + (aligned - 1)) & ~(aligned - 1);
            }

            public IntPtr[] GetNativePtrList()
            {
                if(format == XRImageFormat.kImageMemoryRGBA)
                {
                    int idx = 0;
                    IntPtr[] list = new IntPtr[queueSize];
                    foreach(var ptr in mTextureList)
                    {
                        list[idx] = ptr.Key;
                        idx++;
                    }

                    return list;
                }
                else
                {
                    return null;
                }
            }

            public Texture2D texture(IntPtr key)
            {
                return mTextureList[key];
            }
        }

        private class XRPreviewStream
        {
            static private int mBaseIdx= 0;
            static private Dictionary<int, KeyValuePair<UInt64, XRChannel>> mChannels = new Dictionary<int, KeyValuePair<UInt64, XRChannel>>();

            public XRPreviewStream()
            {
                System.Random random = new System.Random();
                mBaseIdx = random.Next(0, int.MaxValue / 2);
            }

            public int nextChannelIndex() 
            {
                mBaseIdx++;
                return mBaseIdx;
            }
            public XRChannel GetChannelByUid(UInt64 uid)
            {
                foreach (KeyValuePair<int, KeyValuePair<UInt64, XRChannel>> pair in mChannels)
                {
                    if (pair.Value.Key == uid)
                    {
                        //mChannels.Remove(pair.Key);
                        //break;
                        return pair.Value.Value;
                    }
                }
                return null;

            }
            public void addChannel(XRChannel channel, int idx, UInt64 uid)
            {
                mChannels.Add(idx, new KeyValuePair<UInt64, XRChannel>(uid, channel));
            }

            public void removeChannel(UInt64 uid)
            {
                foreach (KeyValuePair<int, KeyValuePair<UInt64, XRChannel>> pair in mChannels)
                {
                    if (pair.Value.Key == uid)
                    {
                        pair.Value.Value.ReleaseAll();
                        mChannels.Remove(pair.Key);
                        break;
                    }
                }
            }
            
            //callback
            [MonoPInvokeCallback(typeof(FXRCameraImageAvailableCallback))]
            public static void cbPreviewDispatcher(IntPtr frame, int length, int format, long timestamp, int width, int height, int idx)
            {
                if (mChannels.ContainsKey(idx))
                {
                    var channel = mChannels[idx].Value; 
                    if (format == (int)XRImageFormat.kImageTextureOES)
                    {
                        int[] tex = new int[1];
                        Marshal.Copy(frame, tex, 0, sizeof(int));
                        channel.callback.onTextureAvailable(tex[0], timestamp);
                    }
                    else if(format == (int)XRImageFormat.kImageMemoryRGBA)
                    {
                        channel.callback.onImageAvailable(channel.texture(frame), timestamp);
                    }
                    else if(format == (int)XRImageFormat.kImageMemoryJPEG)
                    {
                        Debug.Log("11111111   " + length);
                    }
                }
            }
        }

        private class XRPhotoStream
        {
            static private XRChannel mChannel;

            public void replaceChannel(XRChannel channel)
            {
                mChannel = channel;
            }

            //callback
            [MonoPInvokeCallback(typeof(FXRCameraImageAvailableCallback))]
            public static void cbPhotoDispatcher(IntPtr frame, int length, int format, long timestamp, int width, int height, int idx)
            {

                if (format == (int)XRImageFormat.kImageTextureOES)
                {
                    int[] tex = new int[1];
                    Marshal.Copy(frame, tex, 0, sizeof(int));
                    mChannel.callback.onTextureAvailable(tex[0], timestamp);
                }
                else if (format == (int)XRImageFormat.kImageMemoryRGBA)
                {
                    mChannel.callback.onImageAvailable(mChannel.texture(frame), timestamp);
                }
                else if (format == (int)XRImageFormat.kImageMemoryJPEG)
                {
                    mChannel.callback.onImageAvailable(frame, length, timestamp);
                }
            }

        }

        public class XRResolution
        {
            public XRResolution(int w, int h)
            {
                width = w;
                height = h;
            }

            public int width;
            public int height;
        }


        private IntPtr mHandle = IntPtr.Zero;
        private string mCameraID = null;
        private XRPreviewStream mPreviewStream = new XRPreviewStream();
        private XRPhotoStream mPhotoStream = new XRPhotoStream();

        public XRCamera(String id) 
        {
            mCameraID = id;
        }

        public int open()
        {
            if(mHandle != IntPtr.Zero)
            {
                return 0;
            }

            IntPtr handle = XRInterfaces.RayNeoApi_OpenCameraDevice(mCameraID);
            if (handle != IntPtr.Zero)
            {
                mHandle = handle;
                return 0;
            }
            return -1;
        }

        public void close() 
        {
            if(mHandle == IntPtr.Zero)
            {
                return;
            }

            XRInterfaces.RayNeoApi_CloseCameraDevice(mHandle);
            mHandle = IntPtr.Zero;
        }


        public UInt64 startPreviewChannel(int width, int height, XRImageFormat format, ICallback cb)
        {
            if(mHandle == IntPtr.Zero)
            {
                return 0;
            }

            XRChannel channel = new XRChannel(mCameraID, width, height, format, new XRRect(), 0, cb);
            var idx = mPreviewStream.nextChannelIndex();
            var storage = channel.GetNativePtrList();
            var uid = RayNeoApi_StartPreviewChannel(mHandle, width, height, (int)format, Marshal.GetFunctionPointerForDelegate<FXRCameraImageAvailableCallback>(XRPreviewStream.cbPreviewDispatcher), storage, storage != null ? storage.Length : 0, idx);
            if (uid != 0)
            {
                mPreviewStream.addChannel(channel, idx, uid);
            }

            return uid;
        }

        public UInt64 startPreviewChannelWithParameters(int width, int height, int frameRate, XRImageFormat format, Dictionary<XRCameraProperty, long[]> parameters, long flag, ICallback cb) 
        {
            if (mHandle == IntPtr.Zero)
            {
                return 0;
            }

            int[] keys = null;
            int lenOfKeys = 0;
            long[] values = null;
            int[] lenOfEachValue = null;

            if(parameters != null && parameters.Count > 0)
            {
                lenOfKeys = parameters.Count;
                keys = new int[lenOfKeys];
                lenOfEachValue = new int[lenOfKeys];

                int i = 0;
                foreach (KeyValuePair<XRCameraProperty, long[]> pair in parameters)
                {
                    keys[i] = (int)pair.Key;
                    lenOfEachValue[i] = pair.Value.Length;
                    i++;
                }
                values = parameters.Values.SelectMany(valueArray => valueArray).ToArray();
            }

            XRRect roi = new XRRect();
            if(parameters != null && parameters.ContainsKey(XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION))
            {
                roi.x = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][0];
                roi.y = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][1];
                roi.width = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][2];
                roi.height = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][3];
            }

            XRChannel channel = new XRChannel(mCameraID, width, height, format, roi, flag, cb);
            var idx = mPreviewStream.nextChannelIndex();
            var storage = channel.GetNativePtrList();
            var uid = RayNeoApi_StartPreviewChannelWithParameters(mHandle, width, height, frameRate, (int)format, keys, lenOfKeys, values, lenOfEachValue, flag, Marshal.GetFunctionPointerForDelegate<FXRCameraImageAvailableCallback>(XRPreviewStream.cbPreviewDispatcher), storage, storage != null ? storage.Length : 0, idx);
            if (uid != 0)
            {
                mPreviewStream.addChannel(channel, idx, uid);
            }

            return uid;
        }

        public UInt64 startPreviewChannelWithParameters(int width, int height, int frameRate, XRImageFormat format, long flag, ICallback cb)
        {
            return startPreviewChannelWithParameters(width, height, frameRate, format, null, flag, cb);
        }

        public UInt64 startPreviewChannelWithParameters(int width, int height, int frameRate, XRImageFormat format, ICallback cb)
        {
            return startPreviewChannelWithParameters(width, height, frameRate, format, null, (long)XRCameraFlag.XR_CAMERA_FLAG_DEFAULT, cb);
        }

        public int stopPreviewChannel(UInt64 uid)
        {
            if (mHandle == IntPtr.Zero)
            {
                return -1;
            }

            var err = RayNeoApi_StopPreviewChannel(mHandle, uid);
            mPreviewStream.removeChannel(uid);
            return err;
        }

        public int takePicture(int width, int height, XRImageFormat format, ICallback cb)
        {
            if (mHandle == IntPtr.Zero)
            {
                return -1;
            }
            
            XRChannel channel = new XRChannel(mCameraID, width, height, format, new XRRect(), 0, cb, 1);
            mPhotoStream.replaceChannel(channel);
            var storage = channel.GetNativePtrList();
            return RayNeoApi_TakePicture(mHandle, width, height, (int)format, Marshal.GetFunctionPointerForDelegate<FXRCameraImageAvailableCallback>(XRPhotoStream.cbPhotoDispatcher), storage != null ? storage[0] : IntPtr.Zero, 0);
        }

        public int takePictureWithParameters(int width, int height, int frameRate, XRImageFormat format, Dictionary<XRCameraProperty, long[]> parameters, long flag, ICallback cb)
        {
            if (mHandle == IntPtr.Zero)
            {
                return 0;
            }

            int[] keys = null;
            int lenOfKeys = 0;
            long[] values = null;
            int[] lenOfEachValue = null;

            if (parameters != null && parameters.Count > 0)
            {
                lenOfKeys = parameters.Count;
                keys = new int[lenOfKeys];
                lenOfEachValue = new int[lenOfKeys];

                int i = 0;
                foreach (KeyValuePair<XRCameraProperty, long[]> pair in parameters)
                {
                    keys[i] = (int)pair.Key;
                    lenOfEachValue[i] = pair.Value.Length;
                    i++;
                }
                values = parameters.Values.SelectMany(valueArray => valueArray).ToArray();
            }

            XRRect roi = new XRRect();
            if (parameters != null && parameters.ContainsKey(XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION))
            {
                roi.x = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][0];
                roi.y = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][1];
                roi.width = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][2];
                roi.height = (int)parameters[XRCameraProperty.XR_CAMERA_PROPERTY_MEMORY_SOFTWARE_CROP_REGION][3];
            }

            XRChannel channel = new XRChannel(mCameraID, width, height, format, roi, flag, cb, 1);
            mPhotoStream.replaceChannel(channel);
            var storage = channel.GetNativePtrList();
            return RayNeoApi_TakePictureWithParameters(mHandle, width, height, (int)format, keys, lenOfKeys, values, lenOfEachValue, flag, Marshal.GetFunctionPointerForDelegate<FXRCameraImageAvailableCallback>(XRPhotoStream.cbPhotoDispatcher), storage != null ? storage[0] : IntPtr.Zero, 0);
        }
    }

}