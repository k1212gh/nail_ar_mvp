using System;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.InputSystem;

namespace RayNeo
{


    [Serializable]
    public class LiteTouchConfig
    {
        public const uint PowerPixel = 4;
        public RayNeo.API.DeviceType platformType;
        //[Disable]
        //双击.   间隔.
        [Range(0, 1)]
        public float MulitTapSpacing = 0.4f;//走配置.
        public float LongPressSpacing = 0.8f;//走配置.

        //按下到抬起.如果产生了超过该像素的滑动.那么判定为滑动, 不执行点击.
        public uint MovingThreshold = 20 * PowerPixel;//走配置
        public uint MovingUpDownThreshold = 8 * PowerPixel;//走配置
        public uint SwipeEndThreshold = 50 * PowerPixel;//调用swipeEnd的阈值.
        public uint FastSwipeEndThreshold = 120 * PowerPixel;//调用swipeEnd的阈值.
        public bool ReleaseSimpleTapImmediately = false;//如果为true.双击则会先有个单击回调.再有双击
        public bool ReleaseLastTapOnChangeToMove = true;//单击后.手指放下滑动.  立刻执行单击事件.

        //public bool ReleaseDoubleTapImmediately = false;//如果为true,则立即释放doubletouch


        public float SwipXStepTriggerDistance = 50 * PowerPixel;//手势滑动期间的阶段.到达某个像素阈值下发一次事件.
        public float SwipYStepTriggerDistance = 25 * PowerPixel;//手势滑动期间的阶段.到达某个像素阈值下发一次事件.

    }
    public enum TouchActionType
    {
        NONE,
        IN_SWIPE,//是否在swipe中
        LEFT_SWIPE, //左滑
        RIGHT_SWIPE,//右滑
        UP_SWIPE, //上
        DOWN_SWPIE,//下

        //阶段性滑动事件
        LEFT_SWIPE_STEP,
        RIGHT_SWIPE_STEP,
        UP_SWIPE_STEP,
        DOWN_SWIPE_STEP,
        //------------------

        //FAST_LEFT_SWIPE,//快左
        //FAST_RIGHT_SWIPE,//快右
        LONG_PRESS, //长按
        DOUBLE_FINGER_LONG_PRESS, //双指长按.

        LEFT_SWIPE_END, //左滑结束. 走SwipeEndThreshold
        RIGHT_SWIPE_END,//右滑结束.走SwipeEndThreshold
        UP_SWIPE_END, //上结束.走SwipeEndThreshold
        DOWN_SWPIE_END,//下结束.走SwipeEndThreshold
        FAST_LEFT_SWIPE_END,//快左结束.走SwipeEndThreshold
        FAST_RIGHT_SWIPE_END,//快右结束.走SwipeEndThreshold

        TAP1,
        TAP2,
        TAP3,
        ERROR_STATE,//错误状态.什么都不执行.
    }

    public class TouchStateInfo
    {

        public bool FingerIsActiveInThisAction = false;//本次事件是否已经被激活.
        public bool DownState = false;
        public Vector2 Pos;
        public Vector2 DownPos;
        public Vector2 LastPos;//上一个手指位置.
        public Vector2 SwipeStartPos;//执行swpie时.起始点位置.
        public Vector2 SwipeShotStepPos;//阶段性滑动手势的姿态记录.超过阈值就发送事件.
        public long LastClickPerformedTime = 0;
        public long FingerDownTime = 0;
        //public bool preformedTap = false;//本帧是否执行点击.
        public bool preformedTouchUp = false;//是否是touch 抬起.

        public int ClickCount = 0;
        public void Clear()
        {


            FingerIsActiveInThisAction = preformedTouchUp = DownState = false;
            FingerDownTime = LastClickPerformedTime = ClickCount = 0;
        }

    }

    /// <summary>
    /// 单击
    /// 双击
    /// 向前向后滑动
    /// 向上向下滑动
    /// 长按
    /// 双指单击
    /// 双指长按
    /// 
    /// 
    /// 进入某个状态时.拥有错误状态之后.即刻取消.比如双指长按时,一个手指抬起来. 即可取消所有行为
    /// /// 1.超出了点击时间.但是还没到长按时间. 是不执行任何行为的
    /// 2.一旦到达无法理解的操作. 就直接打断行为.
    /// </summary>
    public class SimpleTouchForLite : MonoSingleton<SimpleTouchForLite>
    {
        protected string TAG { get; } = "[SimpleTouchForLite] ";

        RayNeoInput m_Action;

        public bool m_CustomConfig = false;

        public LiteTouchConfig m_TouchConfig;

        [Serializable]
        public class OnTapEvent : UnityEvent { }
        [Serializable]
        public class OnPosEvent : UnityEvent<Vector2> { }


        [Serializable]
        public class OnTouchMoveEvent : UnityEvent<TouchActionType, Vector2> { }


        [SerializeField]
        private OnTapEvent m_OnSimleTap = new OnTapEvent();
        public OnTapEvent OnSimpleTap { get => m_OnSimleTap; }


        [SerializeField]
        private OnTapEvent m_OnDoubleTap = new OnTapEvent();
        public OnTapEvent OnDoubleTap { get => m_OnDoubleTap; }


        [SerializeField]
        private OnTapEvent m_OnTripleTap = new OnTapEvent();
        public OnTapEvent OnTripleTap { get => m_OnTripleTap; }

        //双指单击.
        private OnTapEvent m_OnDoubleFingerTap = new OnTapEvent();
        public OnTapEvent OnDoubleFingerTap { get => m_OnDoubleFingerTap; }


        [SerializeField]
        private OnPosEvent m_OnTouchStart = new OnPosEvent();
        public OnPosEvent OnTouchStart { get => m_OnTouchStart; }

        [SerializeField]
        private OnTouchMoveEvent m_OnTouchMove = new OnTouchMoveEvent();
        public OnTouchMoveEvent OnTouchMove { get => m_OnTouchMove; }

        [SerializeField]
        private OnPosEvent m_OnTouchUp = new OnPosEvent();
        public OnPosEvent OnTouchUp { get => m_OnTouchUp; }

        //滑动行为执行着.但是结束了.
        private OnTouchMoveEvent m_OnSwipEnd = new OnTouchMoveEvent();
        public OnTouchMoveEvent OnSwipEnd { get => m_OnSwipEnd; }


        private UnityEvent m_OnLongPress = new UnityEvent();
        public UnityEvent OnLongPress { get => m_OnLongPress; }



        public TouchActionType m_MoveType = TouchActionType.NONE;//没有状态.

        public TouchStateInfo m_FirstFingerInfo = new TouchStateInfo();
        TouchStateInfo m_SecondFingerInfo = new TouchStateInfo();

        private bool m_ThisActionIsTrash = false;//该标记为true时. 所有行为都不被执行.

        #region OnTouchMoveSelfRightLeftUpDown Event
        //触控
        public UnityEvent<Vector2> OnSwipeLeftEnd = new();
        public UnityEvent<Vector2> OnSwipeRightEnd = new();
        public UnityEvent<Vector2> OnSwipeUpEnd = new();
        public UnityEvent<Vector2> OnSwipeDownEnd = new();

        public UnityEvent<Vector2> OnSwipeLeft = new();
        public UnityEvent<Vector2> OnSwipeRight = new();
        public UnityEvent<Vector2> OnSwipeUp = new();
        public UnityEvent<Vector2> OnSwipeDown = new();
        #endregion

        private void OnEnable()
        {
            m_TouchConfig = new LiteTouchConfig();
            m_TouchConfig.ReleaseSimpleTapImmediately = false;

            if (m_CustomConfig)
            {
            }
            else
            {
                var tc = RayNeoXRGeneralSettings.Instance.SimpleTouchConfig;

            }
            m_Action = new RayNeoInput();
            m_Action.Enable();
            //检查是否按下.
            m_Action.MulitTouch.Touch1Press.performed += Touch1PressPerformed;
            m_Action.MulitTouch.Touch2Press.performed += Touch2PressPerformed;

            m_Action.MulitTouch.Touch1Press.canceled += Touch1PressCanceled;
            m_Action.MulitTouch.Touch2Press.canceled += Touch2PressCanceled;


            //只检查单击行为.
            m_Action.MulitTouch.Touch1Tap.performed += Touch1TapPerformed;

            m_Action.MulitTouch.Touch2Tap.performed += Touch2TapPerformed;

            //检查当前位置.
            m_Action.MulitTouch.Touch1Position.performed += Touch1Performed;
            m_Action.MulitTouch.Touch2Position.performed += Touch2Performed;

            m_OnTouchMove.AddListener(OnTouchMoveSelfRightLeftUpDown);
        }

        private Touchscreen m_TouchedScreen;

        public Vector2 GetTouch1Pos()
        {
            if (Application.isEditor)
            {
                return m_Action.MulitTouch.Touch1Position.ReadValue<Vector2>();

            }
            else
            {
                if (m_TouchedScreen == null)
                {
                    return m_Action.MulitTouch.Touch1Position.ReadValue<Vector2>();
                }
                else
                {
                    return m_TouchedScreen.position.ReadValue();
                }
            }


            return m_Action.MulitTouch.Touch1Position.ReadValue<Vector2>();

        }
        private void Touch1PressPerformed(InputAction.CallbackContext context)
        {

            foreach (var touchscreen in InputSystem.devices)
            {
                if (touchscreen is Touchscreen)
                {
                    var touches = touchscreen as Touchscreen;
                    if (touches.press.isPressed)
                    {
                        // 处理触摸坐标
                        m_TouchedScreen = touches;
                        break;
                    }
                }
            }
            m_FirstFingerInfo.LastPos = m_FirstFingerInfo.Pos = m_FirstFingerInfo.DownPos = GetTouch1Pos();
            if (!m_FirstFingerInfo.DownState)
            {
                OnTouchStart?.Invoke(m_FirstFingerInfo.DownPos);
            }
            m_FirstFingerInfo.FingerIsActiveInThisAction = m_FirstFingerInfo.DownState = true;
            m_FirstFingerInfo.FingerDownTime = CurrentTimeMilliseconds;

            m_SecondFingerInfo.ClickCount = 0;//第一个手指按下. 那么第二个手指的单击也应该被清理.
            UpdateTouchEvent();

        }
        private void Touch2PressPerformed(InputAction.CallbackContext context)
        {
            m_SecondFingerInfo.FingerIsActiveInThisAction = m_SecondFingerInfo.DownState = true;
            m_SecondFingerInfo.LastPos = m_SecondFingerInfo.Pos = m_SecondFingerInfo.DownPos = m_Action.MulitTouch.Touch2Position.ReadValue<Vector2>();
            m_SecondFingerInfo.FingerDownTime = CurrentTimeMilliseconds;

            //当第二个手指按下时.需要清空第一个手指的部分状态. 比如clickcount?
            m_FirstFingerInfo.ClickCount = 0;

        }
        private void Touch1PressCanceled(InputAction.CallbackContext context)
        {
            if (m_FirstFingerInfo.DownState)
            {
                OnTouchUp?.Invoke(m_FirstFingerInfo.DownPos);
            }
            m_FirstFingerInfo.DownState = false;
            m_TouchedScreen = null;


        }
        private void Touch2PressCanceled(InputAction.CallbackContext context)
        {
            m_SecondFingerInfo.DownState = false;

        }

        private void Touch1TapPerformed(InputAction.CallbackContext context)
        {
            m_FirstFingerInfo.ClickCount++;

            m_FirstFingerInfo.LastClickPerformedTime = CurrentTimeMilliseconds;

            if (m_TouchConfig.ReleaseSimpleTapImmediately)
            {
                OnSimpleTapInvoke();
            }

            if (m_FirstFingerInfo.ClickCount == 3)
            {
                OnTripleTapInvoke();//直接执行
                ClearAllState();
            }

        }


        private void Touch2TapPerformed(InputAction.CallbackContext context)
        {
            m_SecondFingerInfo.ClickCount++;
            m_SecondFingerInfo.LastClickPerformedTime = CurrentTimeMilliseconds;

        }


        private void Touch1Performed(InputAction.CallbackContext context)
        {
        }

        private void Touch2Performed(InputAction.CallbackContext context)
        {
            Debug.Log(TAG + "Touch2Performed()  context.ToString() : " + context.ToString());
            if (!m_SecondFingerInfo.DownState)
            {
                return;
            }
            //当前行为被取消.不执行识别.
            if (m_ThisActionIsTrash)
            {
                return;
            }
            m_SecondFingerInfo.Pos = context.ReadValue<Vector2>();

        }


        private void OnDisable()
        {
            m_OnTouchMove.RemoveListener(OnTouchMoveSelfRightLeftUpDown);
            m_Action.Disable();
        }

        private bool FingerIsInAction(TouchStateInfo info)
        {
            //return info.DownState || info.ClickCount > 0;

            return info.FingerIsActiveInThisAction;
        }

        private bool ClickOutofTime(long curTime, long time)
        {
            return (curTime - time) >= (m_TouchConfig.MulitTapSpacing * 1000);
        }


        private void MoveCheck(TouchStateInfo tsi)
        {
            var lastMoveType = m_MoveType;//持续记录上次的移动类型.

            //Debug.LogError("tsi.LastPos.y:" + tsi.LastPos + "  thisY:" + tsi.Pos + " 移动类型:" + m_MoveType);
            if ((m_MoveType == TouchActionType.NONE && ((Mathf.Abs(tsi.DownPos.x - tsi.Pos.x) > m_TouchConfig.MovingThreshold) || Mathf.Abs(tsi.DownPos.y - tsi.Pos.y) > m_TouchConfig.MovingUpDownThreshold)))
            {
                m_MoveType = TouchActionType.IN_SWIPE;
                tsi.SwipeShotStepPos = tsi.SwipeStartPos = tsi.DownPos;
                CheckFlashingOffTouch(lastMoveType, m_MoveType, tsi);
                tsi.LastPos = tsi.Pos;//更新起始点.

            }
            else if (m_MoveType == TouchActionType.IN_SWIPE)
            {
                CheckFlashingOffTouch(lastMoveType, m_MoveType, tsi);
                tsi.LastPos = tsi.Pos;//更新起始点.

            }
            else if ((CurrentTimeMilliseconds - tsi.FingerDownTime) >= (m_TouchConfig.LongPressSpacing * 1000))
            {
                //长按.
                m_MoveType = TouchActionType.LONG_PRESS;
            }
            else
            {
                m_MoveType = TouchActionType.NONE;
            }
        }

        //这里要制作保底. 比如在swip=none时, pixel=100, swip=left时,pixel马上变为1000,触摸还结束了.直接需要跑一次swipe-step事件.
        //或者可以更改SwipeShotStepPos值?
        //触摸快了会产生闪断问题. 100像素直接跳变到300,然后在300徘徊.抬手.
        private void CheckFlashingOffTouch(TouchActionType lastMoveType, TouchActionType currentMoveType, TouchStateInfo tsi)
        {
            if (lastMoveType != TouchActionType.NONE)
            {
                return;
            }

            var delta = tsi.LastPos - tsi.Pos;
            if (Mathf.Abs(delta.x) > m_TouchConfig.SwipXStepTriggerDistance)
            {
                //触发保底.
                tsi.SwipeShotStepPos = new Vector2(tsi.SwipeShotStepPos.x - m_TouchConfig.SwipXStepTriggerDistance - 1, tsi.SwipeShotStepPos.y);//将阶段目标,向下移动可释放1次swip的位置
            }
            else if (-delta.x > m_TouchConfig.SwipXStepTriggerDistance)
            {
                //触发保底.
                tsi.SwipeShotStepPos = new Vector2(tsi.SwipeShotStepPos.x + m_TouchConfig.SwipXStepTriggerDistance + 1, tsi.SwipeShotStepPos.y);//将阶段目标,向下移动可释放1次swip的位置
            }
            else if (delta.y > m_TouchConfig.SwipYStepTriggerDistance)
            {
                //触发保底.
                tsi.SwipeShotStepPos = new Vector2(tsi.SwipeShotStepPos.x, tsi.SwipeShotStepPos.y - m_TouchConfig.SwipYStepTriggerDistance - 1);//将阶段目标,向下移动可释放1次swip的位置
            }
            else if (-delta.y > m_TouchConfig.SwipYStepTriggerDistance)
            {
                //触发保底.
                tsi.SwipeShotStepPos = new Vector2(tsi.SwipeShotStepPos.x, tsi.SwipeShotStepPos.y + m_TouchConfig.SwipYStepTriggerDistance + 1);//将阶段目标,向上移动可释放1次swip的位置
                Debug.Log("SimpleTouchForlite.CheckFlashingOffTouch.DOWN_SWPIE Flashing Off ");

            }

        }

        private void UpdateTouchEvent()
        {
            if (m_ThisActionIsTrash)
            {

                if (!m_FirstFingerInfo.DownState && !m_SecondFingerInfo.DownState)
                {
                    //双指抬起了. 当前行为是垃圾的.就清理掉所有信息.
                    ClearAllState();
                }
                return;

            }

            bool firstFingerActive = FingerIsInAction(m_FirstFingerInfo);
            bool secondFingerActive = FingerIsInAction(m_SecondFingerInfo);
            if (Application.isEditor)
            {
                m_FirstFingerInfo.Pos = GetTouch1Pos();

            }
            else
            {
                if (m_TouchedScreen != null)
                {
                    m_FirstFingerInfo.Pos = GetTouch1Pos();
                }
            }

            long curTime = CurrentTimeMilliseconds;

            if (firstFingerActive && secondFingerActive)
            {


                //双指操作.检查.
                if (m_FirstFingerInfo.ClickCount > 0 && m_SecondFingerInfo.ClickCount > 0)
                {
                    //执行.双指单击.
                    FireDoubleFingerTap();
                }
                else if (m_FirstFingerInfo.DownState && m_SecondFingerInfo.DownState)
                {
                    //双指都按着了.执行
                    if (m_MoveType == TouchActionType.NONE &&
                        (CurrentTimeMilliseconds - m_FirstFingerInfo.FingerDownTime) >= (m_TouchConfig.LongPressSpacing * 1000) &&
                         (CurrentTimeMilliseconds - m_SecondFingerInfo.FingerDownTime) >= (m_TouchConfig.LongPressSpacing * 1000))
                    {
                        //双指长按.
                        m_MoveType = TouchActionType.DOUBLE_FINGER_LONG_PRESS;
                        BeginMoveActionInvoke();
                    }

                }
                else if (m_FirstFingerInfo.DownState)
                {
                    if (ClickOutofTime(curTime, m_SecondFingerInfo.LastClickPerformedTime))
                    {
                        m_ThisActionIsTrash = true;

                        //ClearAllState(); //一个手指抬起了. 但是抬起超过了时间.
                    }
                }
                else if (m_SecondFingerInfo.DownState)
                {
                    if (ClickOutofTime(curTime, m_FirstFingerInfo.LastClickPerformedTime))
                    {
                        m_ThisActionIsTrash = true;

                        //ClearAllState(); //一个手指抬起了. 但是抬起超过了时间.
                    }
                }
                else
                {
                    m_ThisActionIsTrash = true;
                }
            }
            else if (firstFingerActive)
            {

                if (m_MoveType != TouchActionType.NONE || m_FirstFingerInfo.DownState)//检查滑动. 滑动检查完毕. 不对了就清理.
                {
                    //ClearAllState();

                    if (m_FirstFingerInfo.ClickCount > 0 && ClickOutofTime(curTime, m_FirstFingerInfo.FingerDownTime))
                    {
                        m_FirstFingerInfo.ClickCount = 0;//清理点击.
                    }
                    //进入长按或者滑动.
                    MoveCheck(m_FirstFingerInfo);
                    BeginMoveActionInvoke();
                }
                else if (m_FirstFingerInfo.ClickCount > 0 && ClickOutofTime(curTime, m_FirstFingerInfo.LastClickPerformedTime))
                {
                    //执行点击.
                    FireTap(m_FirstFingerInfo.ClickCount);
                }
                else
                {

                }
            }
            else if (secondFingerActive)
            {
                //走到这里应该是非法的.
                m_ThisActionIsTrash = true;
            }
        }
        private void Update()
        {

            UpdateTouchEvent();
        }

        private void BeginMoveActionInvoke()
        {

            if (m_MoveType == TouchActionType.NONE || m_MoveType == TouchActionType.ERROR_STATE)
            {
                return;
            }

            OnTouchMove?.Invoke(m_MoveType, m_FirstFingerInfo.Pos);

            if (m_MoveType == TouchActionType.LONG_PRESS || m_MoveType == TouchActionType.DOUBLE_FINGER_LONG_PRESS)
            {
                m_ThisActionIsTrash = true;
                //ClearAllState();
                OnLongPress.Invoke();
            }
            else if (!m_FirstFingerInfo.DownState)
            {

                var delta = m_FirstFingerInfo.Pos - m_FirstFingerInfo.SwipeShotStepPos;
                delta.x = Mathf.Abs(delta.x);
                delta.y = Mathf.Abs(delta.y);
                switch (m_MoveType)
                {
                    //case TouchActionType.NONE:
                    //    break;
                    case TouchActionType.LEFT_SWIPE:
                        //左滑动是否超过阈值
                        if (delta.x > m_TouchConfig.FastSwipeEndThreshold)
                        {
                            OnSwipEnd?.Invoke(TouchActionType.FAST_LEFT_SWIPE_END, m_FirstFingerInfo.Pos);

                        }
                        else if (delta.x > m_TouchConfig.SwipeEndThreshold)
                        {
                            //左滑动超过阈值 .在这里还可以加事件阈值, 比如超过某个事件. 不执行 end了.
                            OnSwipEnd?.Invoke(TouchActionType.LEFT_SWIPE_END, m_FirstFingerInfo.Pos);
                        }

                        break;
                    case TouchActionType.RIGHT_SWIPE:
                        if (delta.x > m_TouchConfig.FastSwipeEndThreshold)
                        {
                            OnSwipEnd?.Invoke(TouchActionType.FAST_RIGHT_SWIPE_END, m_FirstFingerInfo.Pos);

                        }
                        else if (delta.x > m_TouchConfig.SwipeEndThreshold)
                        {
                            //左滑动超过阈值 .在这里还可以加事件阈值, 比如超过某个事件. 不执行 end了.
                            OnSwipEnd?.Invoke(TouchActionType.RIGHT_SWIPE_END, m_FirstFingerInfo.Pos);
                        }
                        break;
                    case TouchActionType.UP_SWIPE:

                        if (delta.y > m_TouchConfig.SwipeEndThreshold)
                        {
                            //左滑动超过阈值 .在这里还可以加事件阈值, 比如超过某个事件. 不执行 end了.
                            OnSwipEnd?.Invoke(TouchActionType.UP_SWIPE_END, m_FirstFingerInfo.Pos);
                        }
                        break;
                    case TouchActionType.DOWN_SWPIE:
                        if (delta.y > m_TouchConfig.SwipeEndThreshold)
                        {
                            //左滑动超过阈值 .在这里还可以加事件阈值, 比如超过某个事件. 不执行 end了.
                            OnSwipEnd?.Invoke(TouchActionType.DOWN_SWPIE_END, m_FirstFingerInfo.Pos);
                        }
                        break;
                }
                ClearAllState();//手指没有按下就清空.
            }
            else
            {
                //m_TouchConfig
                var swpieStepDelta = m_FirstFingerInfo.Pos - m_FirstFingerInfo.SwipeShotStepPos;
                //发送swip_step事件.
                if (m_MoveType == TouchActionType.IN_SWIPE)
                {
                    if (swpieStepDelta.x >= m_TouchConfig.SwipXStepTriggerDistance)
                    {
                        //left
                        OnTouchMove?.Invoke(TouchActionType.LEFT_SWIPE_STEP, m_FirstFingerInfo.Pos);
                        m_FirstFingerInfo.SwipeShotStepPos = m_FirstFingerInfo.Pos;//这里要分等级? 不能只触发一次? 不行.  只能一次.不然会闪N次
                    }
                    else if (-swpieStepDelta.x >= m_TouchConfig.SwipXStepTriggerDistance)
                    {
                        OnTouchMove?.Invoke(TouchActionType.RIGHT_SWIPE_STEP, m_FirstFingerInfo.Pos);
                        m_FirstFingerInfo.SwipeShotStepPos = m_FirstFingerInfo.Pos;
                    }
                    else if (swpieStepDelta.y >= m_TouchConfig.SwipYStepTriggerDistance)
                    {
                        OnTouchMove?.Invoke(TouchActionType.UP_SWIPE_STEP, m_FirstFingerInfo.Pos);
                        m_FirstFingerInfo.SwipeShotStepPos = m_FirstFingerInfo.Pos;
                    }
                    else if (-swpieStepDelta.y >= m_TouchConfig.SwipYStepTriggerDistance)
                    {
                        OnTouchMove?.Invoke(TouchActionType.DOWN_SWIPE_STEP, m_FirstFingerInfo.Pos);
                        m_FirstFingerInfo.SwipeShotStepPos = m_FirstFingerInfo.Pos;
                    }
                }
            }
        }

        private void FireTap(int clickCount)
        {
            if (clickCount == 0)
            {

            }
            else if (clickCount == 1)
            {
                if (!m_TouchConfig.ReleaseSimpleTapImmediately)
                {
                    OnSimpleTapInvoke();
                }
            }
            else if (clickCount == 2)
            {
                OnDoubleTapInvoke();
            }
            else if (clickCount == 3)
            {
                OnTripleTapInvoke();
            }
            else
            {
                OnSimpleTapInvoke();
            }
            ClearAllState();
        }


        private void OnSimpleTapInvoke()
        {
            Debug.Log("[MercuryX2]SimpleTap");
            OnSimpleTap?.Invoke();
            //WatchGestureUtil.Instance.StartDelayMoveDown();//执行了单击/双击事件之后调用 startDelayMoveDown ，手表滑动不会断掉
        }

        private void OnDoubleTapInvoke()
        {
            Debug.Log("[MercuryX2]DoubleTap");
            OnDoubleTap?.Invoke();//直接执行
            //WatchGestureUtil.Instance.StartDelayMoveDown();//执行了单击/双击事件之后调用 startDelayMoveDown ，手表滑动不会断掉
        }

        private void OnTripleTapInvoke()
        {
            Debug.Log("[MercuryX2]OnTripleTapInvoke");
            OnTripleTap?.Invoke();//直接执行
            //WatchGestureUtil.Instance.StartDelayMoveDown();//执行了单击/双击事件之后调用 startDelayMoveDown ，手表滑动不会断掉
        }


        private void FireDoubleFingerTap()
        {
            OnDoubleFingerTap?.Invoke();
            ClearAllState();
        }

        private void ClearAllState()
        {
            if (m_FirstFingerInfo.DownState)
            {
                OnTouchUp?.Invoke(m_FirstFingerInfo.Pos);
            }

            m_FirstFingerInfo.Clear();
            m_SecondFingerInfo.Clear();

            m_ThisActionIsTrash = false;//还原记录. 允许下一个事件执行.
            m_MoveType = TouchActionType.NONE;
            m_TouchedScreen = null;

        }

        public static long GetMilliseconds(DateTime time)
        {
            return (time.ToUniversalTime().Ticks - 621355968000000000) / 10000;
        }

        public static long CurrentTimeMilliseconds { get => GetMilliseconds(DateTime.Now); }

        private void OnTouchMoveSelfRightLeftUpDown(TouchActionType type, Vector2 pos)
        {
            switch (type)
            {
                //左滑
                case TouchActionType.LEFT_SWIPE_END:
                    OnSwipeRightEnd?.Invoke(pos);
                    break;
                case TouchActionType.LEFT_SWIPE_STEP:
                    Debug.Log(TAG+ "OnTouchMoveSelfRightLeftUpDown: LEFT_SWIPE_STEP");

                    OnSwipeRight?.Invoke(pos);
                    break;
                //右滑
                case TouchActionType.RIGHT_SWIPE_END:
                    OnSwipeLeftEnd?.Invoke(pos);
                    break;
                case TouchActionType.RIGHT_SWIPE_STEP:
                    Debug.Log(TAG + "OnTouchMoveSelfRightLeftUpDown: RIGHT_SWIPE_STEP");
                    OnSwipeLeft?.Invoke(pos);
                    break;

                //上滑
                case TouchActionType.UP_SWIPE_END:
                    OnSwipeUpEnd?.Invoke(pos);
                    break;
                case TouchActionType.UP_SWIPE_STEP:
                    Debug.Log(TAG + "OnTouchMoveSelfRightLeftUpDown: UP_SWIPE_STEP");
                    OnSwipeUp?.Invoke(pos);
                    break;
                //下滑
                case TouchActionType.DOWN_SWPIE_END:
                    OnSwipeDownEnd?.Invoke(pos);
                    break;
                case TouchActionType.DOWN_SWIPE_STEP:
                    Debug.Log(TAG + "OnTouchMoveSelfRightLeftUpDown: DOWN_SWIPE_STEP");
                    OnSwipeDown?.Invoke(pos);
                    break;
            }
        }
    }


}