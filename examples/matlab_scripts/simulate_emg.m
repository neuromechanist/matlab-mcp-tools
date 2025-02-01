function simulate_emg()
    % Set parameters
    fs = 1000;  % Sampling frequency (Hz)
    t = 0:1/fs:10;  % Time vector (10 seconds)
    
    % Generate base signal (random noise)
    base_signal = randn(size(t));
    
    % Add muscle activation bursts
    burst_times = [2 5 7];  % Times for muscle activation bursts
    burst_duration = 0.5;   % Duration of each burst in seconds
    
    % Initialize EMG signal
    emg_signal = base_signal;
    
    % Add bursts of activity
    for i = 1:length(burst_times)
        burst_start = round(burst_times(i) * fs);
        burst_end = round((burst_times(i) + burst_duration) * fs);
        burst_indices = burst_start:burst_end;
        
        % Increase amplitude during bursts
        emg_signal(burst_indices) = emg_signal(burst_indices) * 3;
    end
    
    % Apply bandpass filtering to simulate EMG frequency characteristics
    [b, a] = butter(4, [20 450]/(fs/2), 'bandpass');
    filtered_emg = filtfilt(b, a, emg_signal);
    
    % Plot the results
    h = figure('Visible', 'on');
    plot(t, filtered_emg);
    title('Simulated EMG Signal');
    xlabel('Time (s)');
    ylabel('Amplitude');
    grid on;
    drawnow;
end
