using UnityEngine;

public class RovLeds : MonoBehaviour
{
    [Header("Iþýk Gruplarý")]
    public GameObject[] frontLEDs;
    public GameObject[] backLEDs;
    public GameObject[] leftLEDs;
    public GameObject[] rightLEDs;

    [Header("Test Ayarlarý")]
    public bool isEmergency = false;
    public bool backOnlyTest = true;

    [Header("Zamanlama Ayarý")]
    public int targetFPS = 60;

    // Bunu özellikle geri ekliyoruz.
    // Çünkü SimulasyonVeriAlici.cs bu deðiþkene eriþiyor.
    public float tickRate = 0.1f;

    [Header("Frame Tabanlý Pattern Ayarý")]
    public int framesPerBit = 6;

    private string pFront = "11110000";
    private string pBack = "11001100";
    private string pLeft = "10101010";
    private string pRight = "10011001";
    private string pEmer = "1111111100000000";

    private int startFrame;

    void Start()
    {
        Application.targetFrameRate = targetFPS;
        startFrame = Time.frameCount;

        UpdateFramesPerBit();
    }

    void Update()
    {
        // Eðer baþka script tickRate'i deðiþtirirse framesPerBit de güncel kalsýn.
        UpdateFramesPerBit();

        int elapsedFrames = Time.frameCount - startFrame;
        int bitIndex = elapsedFrames / framesPerBit;

        if (isEmergency)
        {
            bool state = pEmer[bitIndex % pEmer.Length] == '1';

            SetGroup(frontLEDs, state);
            SetGroup(backLEDs, state);
            SetGroup(leftLEDs, state);
            SetGroup(rightLEDs, state);
        }
        else
        {
            bool frontState = pFront[bitIndex % pFront.Length] == '1';
            bool backState = pBack[bitIndex % pBack.Length] == '1';
            bool leftState = pLeft[bitIndex % pLeft.Length] == '1';
            bool rightState = pRight[bitIndex % pRight.Length] == '1';

            if (backOnlyTest)
            {
                SetGroup(frontLEDs, false);
                SetGroup(backLEDs, backState);
                SetGroup(leftLEDs, false);
                SetGroup(rightLEDs, false);
            }
            else
            {
                SetGroup(frontLEDs, frontState);
                SetGroup(backLEDs, backState);
                SetGroup(leftLEDs, leftState);
                SetGroup(rightLEDs, rightState);
            }
        }
    }

    void UpdateFramesPerBit()
    {
        if (targetFPS <= 0)
            targetFPS = 60;

        if (tickRate <= 0f)
            tickRate = 0.1f;

        framesPerBit = Mathf.Max(1, Mathf.RoundToInt(tickRate * targetFPS));
    }

    void SetGroup(GameObject[] leds, bool state)
    {
        foreach (var led in leds)
        {
            if (led != null)
                led.SetActive(state);
        }
    }
}