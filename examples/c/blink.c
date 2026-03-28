/*
 * blink.c - Simulated GPIO blink for Raspberry Pi devcontainer
 *
 * Detects host architecture at compile time and simulates toggling
 * GPIO 17 five times at 0.5-second intervals by printing to stdout.
 */

#include <stdio.h>
#include <stdint.h>
#include <unistd.h>

/* --------------------------------------------------------------------------
 * Compile-time architecture detection
 * -------------------------------------------------------------------------- */
#if defined(__aarch64__)
#  define ARCH_NAME "aarch64 (ARM 64-bit)"
#elif defined(__arm__)
#  define ARCH_NAME "arm (ARM 32-bit)"
#elif defined(__x86_64__)
#  define ARCH_NAME "x86_64 (AMD/Intel 64-bit)"
#else
#  define ARCH_NAME "unknown"
#endif

/* --------------------------------------------------------------------------
 * Simulated GPIO API
 * -------------------------------------------------------------------------- */
#define GPIO_HIGH 1
#define GPIO_LOW  0

/**
 * gpio_set - Simulated GPIO write.
 *
 * On real hardware this would memory-map the BCM peripheral registers and
 * toggle the output latch.  Here we just print the state so the example
 * compiles and runs on any host architecture inside the devcontainer.
 */
static void gpio_set(uint8_t pin, int value)
{
    printf("  GPIO %-3u -> %s\n", (unsigned)pin, value == GPIO_HIGH ? "HIGH" : "LOW");
}

/* --------------------------------------------------------------------------
 * Main
 * -------------------------------------------------------------------------- */
#define LED_PIN          17
#define BLINK_COUNT       5
/* usleep takes microseconds; 500 000 us = 0.5 s */
#define HALF_SECOND_US  500000u

int main(void)
{
    printf("Raspberry Pi GPIO blink example\n");
    printf("Architecture : %s\n", ARCH_NAME);
    printf("LED pin      : GPIO %d\n", LED_PIN);
    printf("Blink count  : %d\n\n", BLINK_COUNT);

    for (int i = 0; i < BLINK_COUNT; i++) {
        printf("Blink %d/%d\n", i + 1, BLINK_COUNT);

        gpio_set(LED_PIN, GPIO_HIGH);
        usleep(HALF_SECOND_US);

        gpio_set(LED_PIN, GPIO_LOW);
        usleep(HALF_SECOND_US);
    }

    printf("\nDone. %d blinks completed.\n", BLINK_COUNT);
    return 0;
}
