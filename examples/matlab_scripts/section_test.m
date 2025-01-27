%% Section 1: Data Generation
% Generate sample data
x = linspace(0, 10, 100);
y = sin(x);

fprintf('Generated %d data points\n', length(x));

%% Section 2: Basic Statistics
% Calculate basic statistics
mean_y = mean(y);
std_y = std(y);
max_y = max(y);
min_y = min(y);

fprintf('Statistics:\n');
fprintf('Mean: %.4f\n', mean_y);
fprintf('Std Dev: %.4f\n', std_y);
fprintf('Max: %.4f\n', max_y);
fprintf('Min: %.4f\n', min_y);

%% Section 3: Plotting
% Create visualization
figure('Position', [100, 100, 800, 400]);

subplot(1, 2, 1);
plot(x, y, 'b-', 'LineWidth', 2);
title('Signal');
xlabel('x');
ylabel('y');
grid on;

subplot(1, 2, 2);
histogram(y, 20);
title('Distribution');
xlabel('Value');
ylabel('Count');
grid on;

sgtitle('Signal Analysis');
