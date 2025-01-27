% Test script for plot generation and capture
x = linspace(0, 2*pi, 100);
y = sin(x);

% Create a figure with some styling
figure;
plot(x, y, 'LineWidth', 2);
title('Sine Wave');
xlabel('x');
ylabel('sin(x)');
grid on;

% Add some annotations
text(pi, 0, '\leftarrow \pi', 'FontSize', 12);
