namespace VL.BasicProcessNode;

/// <summary>
/// Basic stateful counter node example for vvvv gamma.
/// </summary>
[ProcessNode]
public class Counter
{
    private int _value;
    private bool _isInitialized;

    /// <summary>
    /// Increments an internal counter when increment is true.
    /// </summary>
    /// <param name="value">Current counter value.</param>
    /// <param name="increment">When true, adds step to the internal value.</param>
    /// <param name="step">Step size used when incrementing.</param>
    /// <param name="reset">When true, sets the internal value to resetValue.</param>
    /// <param name="resetValue">Value used when reset is triggered.</param>
    public void Update(
        out int value,
        bool increment = false,
        int step = 1,
        bool reset = false,
        int resetValue = 0)
    {
        if (!_isInitialized)
        {
            _value = resetValue;
            _isInitialized = true;
        }

        if (reset)
            _value = resetValue;
        else if (increment)
            _value += step;

        value = _value;
    }
}
