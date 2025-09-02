# 2025

A casual blog to record things I learned on internet related to programming.



https://cs50.harvard.edu/x/2022/
https://cs50.harvard.edu/web/
https://github.com/Asabeneh/30-Days-Of-JavaScript
https://github.com/bradtraversy/design-resources-for-developers



09/02/2025
} catch (e) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

Learned how to fix this problem
Noncompliant code example
function f() {
  try {
    doSomething();
  } catch (err) {
  }
}
Compliant solution
function f() {
  try {
    doSomething();
  } catch (err) {
    console.log(`Exception while doing something: ${err}`);
  }
}


