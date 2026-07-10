public class PermissionUtil
{

    public static void TryQueryPermission(string p)
    {
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(p))
        {
            UnityEngine.Android.Permission.RequestUserPermission(p);

        }
    }
}
