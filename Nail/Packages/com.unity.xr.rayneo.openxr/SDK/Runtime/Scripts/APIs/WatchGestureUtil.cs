using UnityEngine;
using FfalconXR;
using RayNeo.API;

/// <summary>
/// 手表手势封装
/// </summary>
public class WatchGestureUtil : Singleton<WatchGestureUtil>
{

    #region Data


    /// <summary>
    /// TAG
    /// </summary>
    const string TAG = "[WatchGestureUtil] ";

    /// <summary>
    /// AndroidJavaClass
    /// </summary>
    private AndroidJavaClass mJavaClass;
    #endregion


    #region Lifecycle function

    /// <summary>
    /// OnSingletonInit
    /// </summary>
    protected override void OnSingletonInit()
    {
        base.OnSingletonInit();
        mJavaClass = new AndroidJavaClass(PlatformAndroid.SupportPackagePath + ".WatchGestureUtil");
    }

    #endregion

    /// <summary>
    /// 手表手势延迟移动
    /// </summary>
    /// <param name="delayMillis">延迟时间</param>
    public void StartDelayMoveDown(int delayMillis = 1000)
    {
        startDelayMoveDown(delayMillis);
    }


    #region Android Interface

    /**
     * 手表手势延迟移动
     * 执行了单击/双击事件之后调用 startDelayMoveDown ，手表滑动不会断掉
     * （建议 1000 毫秒）
     * @param delayMillis
     */
    protected void startDelayMoveDown(int delayMillis)
    {

        Debug.Log(TAG + "startDelayMoveDown: delayMillis = " + delayMillis);

        mJavaClass.CallStatic("startDelayMoveDown", delayMillis);
    }

    #endregion
}

