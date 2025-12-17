#!/usr/bin/env python3
"""
Sample application that tests all generated Python bindings.

Run:
    # First build the native library
    cmake --preset default && cmake --build --preset default
    
    # Run tests
    python samples/tests/python/samples_test.py
"""

import sys
import os

# Add generated directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'generated'))

from samples import Calculator, Geometry, ShapeProcessor, AsyncProcessor, Point, BoundingBox


def test_calculator():
    """Test Calculator interface"""
    print("Testing Calculator...")
    passed = True
    
    with Calculator() as calc:
        # Basic arithmetic
        result = calc.add(2, 3)
        if result != 5:
            print(f"  FAIL: add(2, 3) = {result}, expected 5")
            passed = False
        else:
            print(f"  PASS: add(2, 3) = {result}")
        
        result = calc.subtract(10, 4)
        if result != 6:
            print(f"  FAIL: subtract(10, 4) = {result}, expected 6")
            passed = False
        else:
            print(f"  PASS: subtract(10, 4) = {result}")
        
        result = calc.multiply(3, 7)
        if result != 21:
            print(f"  FAIL: multiply(3, 7) = {result}, expected 21")
            passed = False
        else:
            print(f"  PASS: multiply(3, 7) = {result}")
        
        result = calc.divide(10.0, 4.0)
        if abs(result - 2.5) > 0.001:
            print(f"  FAIL: divide(10, 4) = {result}, expected 2.5")
            passed = False
        else:
            print(f"  PASS: divide(10.0, 4.0) = {result}")
        
        # Version info
        major = calc.getVersionMajor()
        minor = calc.getVersionMinor()
        print(f"  INFO: Version {major}.{minor}")
    
    return passed


def test_geometry():
    """Test Geometry interface with vector returns"""
    print("\nTesting Geometry...")
    passed = True
    
    with Geometry() as geom:
        # Create line - returns vector of Points
        points = geom.createLine(0, 0, 10, 10, 5)
        if len(points) != 5:
            print(f"  FAIL: createLine returned {len(points)} points, expected 5")
            passed = False
        else:
            print(f"  PASS: createLine returned {len(points)} points")
            for i, p in enumerate(points):
                print(f"    Point[{i}]: ({p.x}, {p.y})")
        
        # Find bounding boxes - returns vector of BoundingBox
        boxes = geom.findBoundingBoxes(3)
        if len(boxes) != 3:
            print(f"  FAIL: findBoundingBoxes returned {len(boxes)} boxes, expected 3")
            passed = False
        else:
            print(f"  PASS: findBoundingBoxes returned {len(boxes)} boxes")
            for i, box in enumerate(boxes):
                print(f"    Box[{i}]: ({box.x}, {box.y}, {box.width}x{box.height}) conf={box.confidence:.2f}")
    
    return passed


def test_shape_processor():
    """Test ShapeProcessor interface with struct parameters"""
    print("\nTesting ShapeProcessor...")
    passed = True
    
    with ShapeProcessor() as proc:
        # Create a bounding box
        box = BoundingBox()
        box.x = 10
        box.y = 20
        box.width = 100
        box.height = 50
        box.confidence = 0.95
        
        # Calculate area
        area = proc.calculateArea(box)
        expected_area = 100 * 50
        if area != expected_area:
            print(f"  FAIL: calculateArea = {area}, expected {expected_area}")
            passed = False
        else:
            print(f"  PASS: calculateArea = {area}")
        
        # Calculate diagonal
        diagonal = proc.calculateDiagonal(box)
        print(f"  INFO: calculateDiagonal = {diagonal:.2f}")
        
        # Translate point
        point = Point()
        point.x = 5
        point.y = 10
        translated = proc.translate(point, 3, 7)
        if translated.x != 8 or translated.y != 17:
            print(f"  FAIL: translate = ({translated.x}, {translated.y}), expected (8, 17)")
            passed = False
        else:
            print(f"  PASS: translate = ({translated.x}, {translated.y})")
        
        # Distance from origin
        dist = proc.distanceFromOrigin(point)
        print(f"  INFO: distanceFromOrigin(5, 10) = {dist}")
        
        # Box contains point
        point_inside = Point()
        point_inside.x = 50
        point_inside.y = 40
        contains = proc.boxContainsPoint(box, point_inside)
        if not contains:
            print(f"  FAIL: boxContainsPoint should be True")
            passed = False
        else:
            print(f"  PASS: boxContainsPoint = {bool(contains)}")
        
        # Create box
        new_box = proc.createBox(1, 2, 30, 40)
        if new_box.x != 1 or new_box.y != 2 or new_box.width != 30 or new_box.height != 40:
            print(f"  FAIL: createBox returned wrong values")
            passed = False
        else:
            print(f"  PASS: createBox = ({new_box.x}, {new_box.y}, {new_box.width}x{new_box.height})")
    
    return passed


def test_async_processor():
    """Test AsyncProcessor interface with callbacks"""
    print("\nTesting AsyncProcessor...")
    passed = True
    
    with AsyncProcessor() as proc:
        # Test progress callback
        progress_calls = []
        def on_progress(current, total):
            progress_calls.append((current, total))
        
        result = proc.processWithProgress(5, on_progress)
        if len(progress_calls) != 5:
            print(f"  FAIL: Progress callback called {len(progress_calls)} times, expected 5")
            passed = False
        else:
            print(f"  PASS: Progress callback called {len(progress_calls)} times")
        
        # Test filter callback
        def is_even(value):
            return value % 2 == 0
        
        count = proc.countFiltered(1, 10, is_even)
        if count != 5:  # 2, 4, 6, 8, 10
            print(f"  FAIL: countFiltered = {count}, expected 5")
            passed = False
        else:
            print(f"  PASS: countFiltered(even) = {count}")
        
        # Test transform callback
        def double_it(value):
            return value * 2
        
        total = proc.sumTransformed(1, 3, double_it)
        expected = 2 + 4 + 6  # 1*2 + 2*2 + 3*2
        if total != expected:
            print(f"  FAIL: sumTransformed = {total}, expected {expected}")
            passed = False
        else:
            print(f"  PASS: sumTransformed(double) = {total}")
    
    return passed


def main():
    print("=== IDL Samples Python Test ===\n")
    
    all_passed = True
    
    all_passed &= test_calculator()
    all_passed &= test_geometry()
    all_passed &= test_shape_processor()
    all_passed &= test_async_processor()
    
    print("\n=== Summary ===")
    if all_passed:
        print("All tests PASSED!")
        return 0
    else:
        print("Some tests FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
