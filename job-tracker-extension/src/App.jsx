import React, { useState } from "react";

function App() {
  console.log("Starting");
  const [status, setStatus] = useState("idle"); // idle, loading, success, error
  const [message, setMessage] = useState("");

  const handleAnalyzeClick = () => {
    setStatus("loading");
    setMessage("Scraping page content...");

    if (typeof chrome !== "undefined" && chrome.tabs) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const activeTab = tabs[0];
        if (!activeTab || !activeTab.id) {
          setStatus("error");
          setMessage("Could not get active tab. Try again.");
          return;
        }

        chrome.scripting.executeScript(
          {
            target: { tabId: activeTab.id },
            func: () => document.body.innerText,
          },
          (injectionResults) => {
            if (
              chrome.runtime.lastError ||
              !injectionResults ||
              injectionResults.length === 0
            ) {
              setStatus("error");
              setMessage("Failed to scrape page. Try refreshing the page.");
              return;
            }

            const pageContent = injectionResults[0].result;
            const jobUrl = activeTab.url;
            console.log("pageContent", pageContent, "jobUrl", jobUrl);
            console.log(typeof pageContent);
            sendToBackend(pageContent, jobUrl);
          }
        );
      });
    } else {
      setStatus("error");
      setMessage("This must be run as a Chrome extension.");
    }
  };

  const sendToBackend = async (pageContent, jobUrl) => {
    setMessage("Analyzing with AI and adding to Notion...");
    try {
      const response = await fetch("http://0.0.0.0:8080/scrape-job", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: jobUrl, page_content: pageContent }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "An unknown error occurred.");
      }

      setStatus("success");
      // setMessage(`Success! Added "${result.data.role}" to Notion.`);
    } catch (error) {
      setStatus("error");
      setMessage(`Error: ${error.message}`);
      console.log("Error sending data to backend:", error);
    }
  };

  return (
    <main className="w-80 h-auto bg-slate-50 p-6 font-sans">
      <div className="text-center">
        <h1 className="text-xl font-bold text-slate-800">AI Job Tracker</h1>
        <p className="text-sm text-slate-600 mt-1">Save this job to Notion</p>
      </div>

      <div className="mt-8">
        <button
          onClick={handleAnalyzeClick}
          disabled={status === "loading"}
          className={`w-full px-4 py-3 text-white font-semibold rounded-lg shadow-md transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2
            ${
              status === "loading"
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700 focus:ring-blue-500"
            }
            ${
              status === "success"
                ? "bg-green-600 hover:bg-green-700 focus:ring-green-500"
                : ""
            }
            ${
              status === "error"
                ? "bg-red-600 hover:bg-red-700 focus:ring-red-500"
                : ""
            }
          `}
        >
          {status === "loading" ? "Processing..." : "Analyze Job Posting"}
        </button>
      </div>

      {message && (
        <div className="mt-4 text-center text-sm text-slate-700">
          <p>{message}</p>
        </div>
      )}
    </main>
  );
}

export default App;
