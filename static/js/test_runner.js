// Test Runner for Molecular Viewer
class TestRunner {
    constructor(viewer) {
        this.viewer = viewer;
        this.tests = [];
        this.results = [];
        this.running = false;
        this.socket = null;
        this.setupTests();
        this.initSocketIO();
    }

    // Initialize Socket.IO connection for test runner
    initSocketIO() {
        this.socket = io({
            transports: ["polling"],
            upgrade: false
        });

        this.socket.on("start_tests", () => {
            console.log("Received start_tests signal");
            this.runAllTests();
        });
    }

    // Set up the test suite
    setupTests() {
        this.tests = [
            {
                name: "Load PDB (1CRN)",
                run: async () => {
                    await this.viewer.loadPdb("1CRN");
                    return { 
                        success: true, 
                        details: "Loaded Crambin (1CRN) structure" 
                    };
                }
            },
            {
                name: "Load PDB and Highlight Hetero (1HSG)",
                run: async () => {
                    await this.viewer.loadPdb("1HSG");
                    await this.viewer.highlightHetero();
                    return { 
                        success: true, 
                        details: "Loaded HIV protease (1HSG) and highlighted hetero atoms" 
                    };
                }
            },
            {
                name: "Rotate X-axis",
                run: async () => {
                    await this.viewer.rotate(90, 0, 0);
                    return { 
                        success: true, 
                        details: "Rotated molecule 90° around X-axis" 
                    };
                }
            },
            {
                name: "Rotate Y-axis",
                run: async () => {
                    await this.viewer.rotate(0, 45, 0);
                    return { 
                        success: true, 
                        details: "Rotated molecule 45° around Y-axis" 
                    };
                }
            },
            {
                name: "Rotate Z-axis",
                run: async () => {
                    await this.viewer.rotate(0, 0, 30);
                    return { 
                        success: true, 
                        details: "Rotated molecule 30° around Z-axis" 
                    };
                }
            },
            {
                name: "Zoom",
                run: async () => {
                    await this.viewer.zoom(1.4);
                    return { 
                        success: true, 
                        details: "Zoomed in with factor 1.4" 
                    };
                }
            },
            {
                name: "Add Box",
                run: async () => {
                    await this.viewer.addBox(
                        { x: 0, y: 0, z: 0 },
                        { x: 10, y: 10, z: 10 }
                    );
                    return { 
                        success: true, 
                        details: "Added 10x10x10 box at origin" 
                    };
                }
            },
            {
                name: "Set Custom Style",
                run: async () => {
                    await this.viewer.setStyle(
                        { chain: "A" },
                        { stick: {}, cartoon: {} }
                    );
                    return { 
                        success: true, 
                        details: "Applied custom style to chain A" 
                    };
                }
            },
            {
                name: "Show Surface (4FNT)",
                run: async () => {
                    await this.viewer.loadPdb("4FNT");
                    await this.viewer.showSurface();
                    return { 
                        success: true, 
                        details: "Loaded 4FNT and showed molecular surface" 
                    };
                }
            },
            {
                name: "Reset View",
                run: async () => {
                    await this.viewer.resetView();
                    return { 
                        success: true, 
                        details: "Reset view to default" 
                    };
                }
            }
        ];
    }

    // Run a single test
    async runTest(test) {
        console.log(`Running test: ${test.name}`);
        
        try {
            // Update UI to show test is running
            this.updateTestStatus(test.name, "running");
            
            // Run the test
            const result = await test.run();
            
            // Wait a bit for any animations to complete
            await new Promise(resolve => setTimeout(resolve, 500));
            
            // Take a screenshot of the result
            const image = this.viewer.takeScreenshot();
            
            // Verify the test result visually by checking if the image exists
            if (!image) {
                throw new Error("Failed to capture screenshot of test result");
            }
            
            // Record the result
            const testResult = {
                name: test.name,
                success: result.success,
                image: image,
                details: result.details || "",
                timestamp: new Date().toISOString()
            };
            
            // Perform additional visual verification specific to each test type
            if (test.name.includes("Rotate") && !result.hasOwnProperty('skipValidation')) {
                console.log("Validating rotation result...");
                
                // For rotation tests, capture viewer state to verify rotation occurred
                const viewState = this.viewer.getViewerState();
                if (!viewState || !viewState.rotationChanged) {
                    throw new Error("Rotation did not apply correctly to the molecule");
                }
                
                // Additional verification for specific axes
                if (test.name.includes("X-axis") && !viewState.xRotated) {
                    throw new Error("X-axis rotation not detected");
                }
                
                if (test.name.includes("Y-axis") && !viewState.yRotated) {
                    throw new Error("Y-axis rotation not detected");
                }
                
                if (test.name.includes("Z-axis") && !viewState.zRotated) {
                    throw new Error("Z-axis rotation not detected");
                }
            }
            
            if (test.name.includes("Box") && !result.hasOwnProperty('skipValidation')) {
                console.log("Validating box display...");
                
                // Verify box was added to viewer
                if (!this.viewer.hasBox()) {
                    throw new Error("Box was not added to the viewer");
                }
                
                // Check if box info is displayed in the UI
                const boxInfo = document.getElementById("boxinfo");
                if (!boxInfo || boxInfo.style.display === "none") {
                    throw new Error("Box information is not displayed in the UI");
                }
                
                // Verify box dimensions
                if (!this.viewer.validateBox({x: 0, y: 0, z: 0}, {x: 10, y: 10, z: 10})) {
                    throw new Error("Box dimensions or location are incorrect");
                }
            }
            
            if (test.name.includes("Reset") && !result.hasOwnProperty('skipValidation')) {
                console.log("Validating view reset...");
                
                // Verify the view was reset
                const viewState = this.viewer.getViewerState();
                if (!viewState || !viewState.wasReset) {
                    throw new Error("View was not properly reset");
                }
                
                // Check if any box is hidden after reset
                const boxInfo = document.getElementById("boxinfo");
                if (boxInfo && boxInfo.style.display !== "none") {
                    throw new Error("Box should be hidden after reset");
                }
                
                // Check if shapes were cleared
                if (!viewState.shapesCleared) {
                    throw new Error("Shapes were not cleared during reset");
                }
            }
            
            // Update the UI with the result
            this.updateTestStatus(test.name, result.success ? "success" : "failed", testResult);
            
            // Send result to server
            this.reportTestResult(testResult);
            
            return testResult;
        } catch (error) {
            console.error(`Test failed: ${test.name}`, error);
            
            // Record the failure
            const testResult = {
                name: test.name,
                success: false,
                image: this.viewer.takeScreenshot() || "", // Capture current state even on failure
                details: `Error: ${error.message}`,
                timestamp: new Date().toISOString()
            };
            
            // Update the UI with the failure
            this.updateTestStatus(test.name, "failed", testResult);
            
            // Send failure to server
            this.reportTestResult(testResult);
            
            return testResult;
        }
    }

    // Run all tests sequentially
    async runAllTests() {
        if (this.running) {
            console.warn("Tests already running");
            return;
        }
        
        this.running = true;
        this.results = [];
        
        // Clear previous results
        await fetch('/api/clear_test_results', { method: 'POST' });
        
        // Update UI to show tests are starting
        this.updateAllTestsStatus("pending");
        document.getElementById("run-tests-btn").disabled = true;
        document.getElementById("test-progress").style.display = "block";
        document.getElementById("test-results-container").style.display = "block";
        
        try {
            // Run each test in sequence
            for (let i = 0; i < this.tests.length; i++) {
                const test = this.tests[i];
                document.getElementById("test-progress-bar").style.width = `${(i / this.tests.length) * 100}%`;
                
                const result = await this.runTest(test);
                this.results.push(result);
            }
            
            // Update progress bar to 100% when done
            document.getElementById("test-progress-bar").style.width = "100%";
            
            // Show final summary
            this.showTestSummary();
            
        } catch (error) {
            console.error("Error running tests:", error);
        } finally {
            this.running = false;
            document.getElementById("run-tests-btn").disabled = false;
        }
    }

    // Update the status of a single test in the UI
    updateTestStatus(testName, status, result = null) {
        // Find or create the test row
        let testRow = document.getElementById(`test-${this.getTestId(testName)}`);
        
        if (!testRow) {
            // Create a new row for this test
            const resultsBody = document.getElementById("test-results-body");
            testRow = document.createElement("tr");
            testRow.id = `test-${this.getTestId(testName)}`;
            
            // Add cells for name, status, and details
            testRow.innerHTML = `
                <td>${testName}</td>
                <td class="status-cell"></td>
                <td class="details-cell"></td>
                <td class="image-cell"></td>
            `;
            
            resultsBody.appendChild(testRow);
        }
        
        // Update the status cell
        const statusCell = testRow.querySelector(".status-cell");
        statusCell.innerHTML = this.getStatusBadge(status);
        
        // If result is provided, update details and image
        if (result) {
            const detailsCell = testRow.querySelector(".details-cell");
            detailsCell.textContent = result.details;
            
            const imageCell = testRow.querySelector(".image-cell");
            if (result.image) {
                imageCell.innerHTML = `<img src="${result.image}" alt="${testName}" class="test-result-image">`;
            }
        }
    }

    // Update all test status to pending
    updateAllTestsStatus(status) {
        const resultsBody = document.getElementById("test-results-body");
        resultsBody.innerHTML = "";
        
        this.tests.forEach(test => {
            this.updateTestStatus(test.name, status);
        });
    }

    // Show a summary of all test results
    showTestSummary() {
        const totalTests = this.results.length;
        const passedTests = this.results.filter(r => r.success).length;
        
        const summaryElement = document.getElementById("test-summary");
        summaryElement.innerHTML = `
            <div class="alert ${passedTests === totalTests ? 'alert-success' : 'alert-warning'}">
                <strong>Test Results:</strong> ${passedTests} of ${totalTests} tests passed
            </div>
        `;
    }

    // Report test result to server
    reportTestResult(result) {
        const payload = {
            ...result,
            is_test: true
        };
        
        this.socket.emit("command", payload, (response) => {
            console.log("Test result reported:", response);
        });
    }

    // Helper to generate test ID from name
    getTestId(testName) {
        return testName.toLowerCase().replace(/[^a-z0-9]/g, '-');
    }

    // Helper to generate status badge HTML
    getStatusBadge(status) {
        const badges = {
            pending: '<span class="badge bg-secondary">Pending</span>',
            running: '<span class="badge bg-info">Running</span>',
            success: '<span class="badge bg-success">Success</span>',
            failed: '<span class="badge bg-danger">Failed</span>'
        };
        return badges[status] || badges.pending;
    }
}

// Initialize the test runner when the DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    // Wait for the viewer to be initialized
    const waitForViewer = setInterval(() => {
        if (window.molecularViewer) {
            clearInterval(waitForViewer);
            
            // Create test runner
            const testRunner = new TestRunner(window.molecularViewer);
            window.testRunner = testRunner;
            
            // Set up run tests button
            const runTestsBtn = document.getElementById("run-tests-btn");
            if (runTestsBtn) {
                runTestsBtn.addEventListener("click", () => {
                    testRunner.runAllTests();
                });
            }
        }
    }, 100);
});
