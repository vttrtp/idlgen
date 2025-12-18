#pragma once

#include "samples_c_api.h"

#include <cmath>
#include <functional>
#include <string>
#include <vector>

namespace samples {

// Callback type aliases for C++ usage
using ProgressCallback = std::function<void(int current, int total)>;
using FilterCallback = std::function<bool(int value)>;
using TransformCallback = std::function<int(int value)>;
using ImageCallback = std::function<bool(const ImageData&)>;

/**
 * @brief Simple calculator for testing numeric types
 */
class SAMPLES_API Calculator {
public:
    Calculator() = default;

    [[nodiscard]] int add(int a, int b) const { return a + b; }
    [[nodiscard]] int subtract(int a, int b) const { return a - b; }
    [[nodiscard]] int multiply(int a, int b) const { return a * b; }
    [[nodiscard]] double divide(double a, double b) const { return b != 0.0 ? a / b : 0.0; }

    [[nodiscard]] int getTotal() const { return total_; }

    [[nodiscard]] int getVersionMajor() const { return 1; }
    [[nodiscard]] int getVersionMinor() const { return 0; }

private:
    int total_ = 0;
};

/**
 * @brief Geometry helper for testing vector returns
 */
class SAMPLES_API Geometry {
public:
    Geometry() = default;

    [[nodiscard]] std::vector<Point> createLine(int x1, int y1, int x2, int y2, int numPoints) {
        std::vector<Point> points;
        if (numPoints <= 0) {
            lastCount_ = 0;
            return points;
        }
        
        points.reserve(numPoints);
        for (int i = 0; i < numPoints; ++i) {
            double t = (numPoints == 1) ? 0.0 : static_cast<double>(i) / (numPoints - 1);
            Point p;
            p.x = static_cast<int>(x1 + t * (x2 - x1));
            p.y = static_cast<int>(y1 + t * (y2 - y1));
            points.push_back(p);
        }
        
        lastCount_ = static_cast<int>(points.size());
        return points;
    }

    [[nodiscard]] std::vector<BoundingBox> findBoundingBoxes(int count) {
        std::vector<BoundingBox> boxes;
        if (count <= 0) {
            lastCount_ = 0;
            return boxes;
        }
        
        boxes.reserve(count);
        for (int i = 0; i < count; ++i) {
            BoundingBox box;
            box.x = i * 10;
            box.y = i * 10;
            box.width = 50 + i;
            box.height = 50 + i;
            box.confidence = 0.9 - (i * 0.1);
            boxes.push_back(box);
        }
        
        lastCount_ = static_cast<int>(boxes.size());
        return boxes;
    }

    [[nodiscard]] int getLastCount() const { return lastCount_; }

private:
    int lastCount_ = 0;
};

/**
 * @brief Shape processor for testing struct parameters
 */
class SAMPLES_API ShapeProcessor {
public:
    ShapeProcessor() = default;

    [[nodiscard]] int calculateArea(BoundingBox box) const {
        return box.width * box.height;
    }

    [[nodiscard]] double calculateDiagonal(const BoundingBox& box) const {
        return std::sqrt(static_cast<double>(box.width * box.width + box.height * box.height));
    }

    [[nodiscard]] Point translate(Point p, int dx, int dy) const {
        return {p.x + dx, p.y + dy};
    }

    [[nodiscard]] int distanceFromOrigin(const Point& p) const {
        return static_cast<int>(std::sqrt(static_cast<double>(p.x * p.x + p.y * p.y)));
    }

    [[nodiscard]] bool boxContainsPoint(const BoundingBox& box, const Point& point) const {
        return point.x >= box.x && point.x < box.x + box.width &&
               point.y >= box.y && point.y < box.y + box.height;
    }

    [[nodiscard]] BoundingBox createBox(int x, int y, int width, int height) const {
        return {x, y, width, height, 1.0};
    }
};

/**
 * @brief Async processor for testing callback support
 */
class SAMPLES_API AsyncProcessor {
public:
    AsyncProcessor() = default;

    [[nodiscard]] int processWithProgress(int count, ProgressCallback onProgress) {
        for (int i = 0; i < count; ++i) {
            onProgress(i, count);
        }
        return count;
    }

    [[nodiscard]] int countFiltered(int start, int end, FilterCallback filter) {
        int count = 0;
        for (int i = start; i <= end; ++i) {
            if (filter(i)) {
                ++count;
            }
        }
        return count;
    }

    [[nodiscard]] int sumTransformed(int start, int end, TransformCallback transform) {
        int sum = 0;
        for (int i = start; i <= end; ++i) {
            sum += transform(i);
        }
        return sum;
    }
};

/**
 * @brief Image processor for testing pointer and reference parameters
 */
class SAMPLES_API ImageProcessor {
public:
    ImageProcessor() = default;

    // Process raw data pointer (e.g., image bytes)
    [[nodiscard]] int processRawData(const uint8_t* data, int size) {
        if (!data || size <= 0) return 0;
        int sum = 0;
        for (int i = 0; i < size; ++i) {
            sum += data[i];
        }
        return sum;
    }

    // Read pixel from raw data
    [[nodiscard]] int readPixel(const uint8_t* data, int width, int x, int y) {
        if (!data || width <= 0) return -1;
        return data[y * width + x];
    }

    // Normalize box in place (clamp to image bounds)
    [[nodiscard]] bool normalizeBox(BoundingBox* box, int maxWidth, int maxHeight) {
        if (!box) return false;
        if (box->x < 0) box->x = 0;
        if (box->y < 0) box->y = 0;
        if (box->x + box->width > maxWidth) box->width = maxWidth - box->x;
        if (box->y + box->height > maxHeight) box->height = maxHeight - box->y;
        return true;
    }

    // Get aspect ratio from const pointer
    [[nodiscard]] double getBoxAspectRatio(const BoundingBox* box) {
        if (!box || box->height == 0) return 0.0;
        return static_cast<double>(box->width) / box->height;
    }

    // Clone box - caller owns returned memory
    [[nodiscard]] BoundingBox* cloneBox(const BoundingBox& source) {
        auto* copy = new BoundingBox();
        copy->x = source.x;
        copy->y = source.y;
        copy->width = source.width;
        copy->height = source.height;
        copy->confidence = source.confidence;
        return copy;
    }

    // Get image size from struct reference
    [[nodiscard]] int getImageSize(const ImageData& info) {
        return info.width * info.height * info.channels;
    }

    // Process images with callback
    [[nodiscard]] int processImages(int count, ImageCallback callback) {
        int processed = 0;
        for (int i = 0; i < count; ++i) {
            ImageData img{100 + i, 100 + i, 3};
            if (callback(img)) {
                ++processed;
            }
        }
        return processed;
    }
};

/**
 * @brief Object manager for testing class object parameters
 */
class SAMPLES_API ObjectManager {
public:
    ObjectManager() = default;

    // Use calculator by pointer
    [[nodiscard]] int useCalculator(Calculator* calc, int a, int b) {
        if (!calc) return 0;
        return calc->add(a, b);
    }

    // Inspect calculator by const pointer
    [[nodiscard]] double inspectCalculator(const Calculator* calc) {
        if (!calc) return 0.0;
        return static_cast<double>(calc->getVersionMajor()) + 
               static_cast<double>(calc->getVersionMinor()) / 10.0;
    }

    // Get version from const reference
    [[nodiscard]] int getCalculatorVersion(const Calculator& calc) {
        return calc.getVersionMajor() * 100 + calc.getVersionMinor();
    }

    // Create new calculator - caller owns memory
    [[nodiscard]] Calculator* createCalculator() {
        return new Calculator();
    }

    // Combine results from two calculators
    [[nodiscard]] int combineResults(const Calculator& calc1, const Calculator& calc2) {
        return calc1.getTotal() + calc2.getTotal();
    }
};

/**
 * @brief Task processor for testing enum parameters
 */
class SAMPLES_API TaskProcessor {
public:
    TaskProcessor() : status_(Status_Unknown) {}

    // Get current status
    [[nodiscard]] Status getStatus() const { return status_; }

    // Set status
    bool setStatus(Status status) {
        status_ = status;
        return true;
    }

    // Get color by index
    [[nodiscard]] Color getColorByIndex(int index) {
        switch (index % 3) {
            case 0: return Color_Red;
            case 1: return Color_Green;
            default: return Color_Blue;
        }
    }

    // Check if color is primary
    [[nodiscard]] bool isPrimaryColor(Color color) {
        // All RGB colors are primary in this context
        return color == Color_Red || color == Color_Green || color == Color_Blue;
    }

    // Convert status to string
    [[nodiscard]] std::string statusToString(Status status) {
        switch (status) {
            case Status_Unknown: return "Unknown";
            case Status_Pending: return "Pending";
            case Status_Active: return "Active";
            case Status_Completed: return "Completed";
            case Status_Failed: return "Failed";
            default: return "Invalid";
        }
    }

    // Parse status from code
    [[nodiscard]] Status statusFromCode(int code) {
        switch (code) {
            case 0: return Status_Unknown;
            case 1: return Status_Pending;
            case 10: return Status_Active;
            case 20: return Status_Completed;
            case 100: return Status_Failed;
            default: return Status_Unknown;
        }
    }

private:
    Status status_;
};

} // namespace samples
