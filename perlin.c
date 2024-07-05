#include <stdio.h>
#include <stdlib.h>
#include <math.h>

typedef struct
{
    float x, y;
} vector2;

float interpolate(float a0, float a1, float w);
vector2 randomGradient(int ix, int iy);
float dotGridGradient(int ix, int iy, float x, float y);
float perlin(float x, float y);

const int ZOOM = 128;
const int IMAGE_SIZE = 1024;

int main(int argc, char *argv[])
{
    // Handle args

    if (argc != 2)
    {
        printf("Usage: .\\perlin.exe [seed]");
        return (1);
    }
    const int SEED = atoi(argv[1]);

    // Image

    FILE *image = fopen("perlin.ppm", "w");
    fprintf(image, "P6\n%i %i\n255\n", IMAGE_SIZE, IMAGE_SIZE);

    // Render

    for (int j = IMAGE_SIZE - 1; j >= 0; j--)
    {
        for (int i = 0; i < IMAGE_SIZE; i++)
        {
            float x = ((float)i / ZOOM) + SEED;
            float y = ((float)j / ZOOM) + SEED;

            unsigned char value = floor(perlin(x, y) * 128) + 127;

            fprintf(image, "%c%c%c", value, value, value);
        }
    }

    fclose(image);
}

/* Function to linearly interpolate between a0 and a1
 * Weight w should be in the range [0.0, 1.0]
 */
float interpolate(float a0, float a1, float w)
{
    if (0.0 > w)
        return a0;
    if (1.0 < w)
        return a1;

    // Interpolates with smoother step algorithm
    return (a1 - a0) * ((w * (w * 6.0 - 15.0) + 10.0) * w * w * w) + a0;
}

/* Create pseudorandom direction vector
 */
vector2 randomGradient(int ix, int iy)
{
    // No precomputed gradients mean this works for any number of grid coordinates
    const unsigned w = 8 * sizeof(unsigned);
    const unsigned s = w / 2; // rotation width
    unsigned a = ix, b = iy;
    a *= 3284157443;
    b ^= a << s | a >> w - s;
    b *= 1911520717;
    a ^= b << s | b >> w - s;
    a *= 2048419325;
    float random = a * (3.14159265 / ~(~0u >> 1)); // in [0, 2*Pi]
    vector2 v;
    v.x = cos(random);
    v.y = sin(random);
    return v;
}

// Computes the dot product of the distance and gradient vectors.
float dotGridGradient(int ix, int iy, float x, float y)
{
    // Get gradient from integer coordinates
    vector2 gradient = randomGradient(ix, iy);

    // Compute the distance vector
    float dx = x - (float)ix;
    float dy = y - (float)iy;

    // Compute the dot-product
    return (dx * gradient.x + dy * gradient.y);
}

// Compute Perlin noise at coordinates x, y
float perlin(float x, float y)
{
    // Determine grid cell coordinates
    int x0 = (int)floor(x);
    int x1 = x0 + 1;
    int y0 = (int)floor(y);
    int y1 = y0 + 1;

    // Determine interpolation weights
    float sx = x - (float)x0;
    float sy = y - (float)y0;

    // Interpolate between grid point gradients
    float n0, n1, ix0, ix1, value;

    n0 = dotGridGradient(x0, y0, x, y);
    n1 = dotGridGradient(x1, y0, x, y);
    ix0 = interpolate(n0, n1, sx);

    n0 = dotGridGradient(x0, y1, x, y);
    n1 = dotGridGradient(x1, y1, x, y);
    ix1 = interpolate(n0, n1, sx);

    value = interpolate(ix0, ix1, sy);

    return value;
}